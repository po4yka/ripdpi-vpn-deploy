"""Exact local Xray endpoint selection, typed profiles, faults and rollback."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from test_xhttp_endpoint_contract_native import fixture, exported_outbound, publish

pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize("mode", ["auto", "packet-up", "stream-up"])
@pytest.mark.parametrize("xmux", [None, {"maxConnections": 2, "hMaxRequestTimes": 8, "hMaxReusableSecs": 2}])
def test_delivered_endpoints_profiles_faults_and_rollback(mode, xmux):
    assert os.geteuid() == 0 and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    stack = fixture.NativeStack()
    publication = Path("/var/lib/vpn-nginx-publication") / (stack.token + "-nginx.service")
    assert not publication.exists()
    try:
        stack.start()
        stack.start_frontend("p1", fallback=True, mode=mode, xmux=xmux, alternate_name="alternate.example")
        selected = [exported_outbound(stack, alternate=alternate) for alternate in (False, True)]
        assert [o["streamSettings"]["tlsSettings"]["serverName"] for o in selected] == ["owned.example", "alternate.example"]
        metrics = []
        for alternate, outbound in enumerate(selected):
            assert outbound["streamSettings"]["xhttpSettings"]["mode"] == mode
            if xmux:
                assert outbound["streamSettings"]["xhttpSettings"]["xmux"] == xmux
            started = time.monotonic()
            port = stack.start_client("p1", outbound=outbound)
            time.sleep(.5)
            stack.run_driver(port)
            # Idle then fresh sessions on the same exact native process.
            time.sleep(3)
            stack.run_driver(port)
            transfer = subprocess.run(["ip", "netns", "exec", stack.namespace, sys.executable,
                str(Path(__file__).resolve().parents[1] / "integration/xhttp_delivery_matrix/transfer.py"), str(port)],
                capture_output=True, text=True, timeout=35)
            assert transfer.returncode == 0, "authenticated bulk transfer failed"
            measured = json.loads(transfer.stdout)
            assert measured["upload_bytes"] == measured["download_bytes"] == 4194304
            pid = int(fixture.command(["systemctl", "show", stack.token + "-frontend", "--property=MainPID", "--value"]))
            status = Path(f"/proc/{pid}/status").read_text()
            rss = int(next(line.split()[1] for line in status.splitlines() if line.startswith("VmRSS:")))
            descriptors = len(list(Path(f"/proc/{pid}/fd").iterdir()))
            assert rss < 262144 and descriptors < 256, "native frontend resource budget exceeded"
            elapsed = time.monotonic() - started
            assert elapsed < 85, "bounded authenticated transfer/reconnect exhausted"
            metrics.append({"endpoint": "alternate" if alternate else "primary", "seconds": round(elapsed, 3), "transfer": measured, "rss_kib": rss, "descriptors": descriptors})
            rejected = stack.start_client("p1", True, outbound=outbound)
            time.sleep(.5)
            stack.run_driver(rejected, True)
        # Refuse wrong TLS identity with the same locally trusted CA.
        wrong = deepcopy(selected[1])
        wrong["streamSettings"]["tlsSettings"]["serverName"] = "wrong.example"
        wrong_port = stack.start_client("p1", outbound=wrong)
        time.sleep(.5)
        stack.run_driver(wrong_port, True)
        # Block only primary ingress inside the owned namespace; alternate
        # completion never overwrites the independently red primary observation.
        fixture.command(["ip", "netns", "exec", stack.namespace, "nft", "add", "table", "inet", "matrix"])
        fixture.command(["ip", "netns", "exec", stack.namespace, "nft", "add", "chain", "inet", "matrix", "input",
                         "{ type filter hook input priority -10; policy accept; }"])
        fixture.command(["ip", "netns", "exec", stack.namespace, "nft", "add", "rule", "inet", "matrix", "input",
                         "tcp", "dport", "8443", "reject"])
        primary = stack.start_client("p1", outbound=selected[0])
        alternate = stack.start_client("p1", outbound=selected[1])
        time.sleep(.5)
        stack.run_driver(primary, True)
        stack.run_driver(alternate)
        fixture.command(["ip", "netns", "exec", stack.namespace, "nft", "delete", "table", "inet", "matrix"])
        # Real rejected ingress authority retains both endpoint generations.
        assert publish(stack).returncode == 0
        rejected = publish(stack, invalid=True)
        assert rejected.returncode != 0
        stack.run_driver(primary)
        stack.run_driver(alternate)
        ordinary = "\n".join(p.read_text(errors="replace") for p in stack.library.glob("vpn-xhttp*.log"))
        assert stack.uuid not in ordinary and stack.values["xray"]["xhttp_path"] not in ordinary
        print(json.dumps({"mode": mode, "xmux": xmux, "observations": metrics}, sort_keys=True))
    finally:
        stack.close()
        if publication.exists():
            shutil.rmtree(publication)
