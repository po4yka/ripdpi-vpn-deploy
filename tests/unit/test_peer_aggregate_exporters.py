"""Aggregate-only AmneziaWG and Hysteria2 peer exporters."""

from __future__ import annotations

import http.server
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AWG_EXPORTER = ROOT / "ansible/roles/amneziawg/files/awg-handshake-exporter.py"
HYSTERIA_EXPORTER = ROOT / "ansible/roles/hysteria/files/hysteria-traffic-exporter.py"
MANIFEST = ROOT / "contract/observability-metric-manifest.example.json"

PEER_KEYS = [
    "QWxwaGFQZWVyS2V5Rml4dHVyZVZhbHVlMDAwMDAwMDA=",
    "QnJhdm9QZWVyS2V5Rml4dHVyZVZhbHVlMDAwMDAwMDA=",
    "Q2hhcmxpZVBlZXJLZXlGaXh0dXJlVmFsdWUwMDAwMDA=",
]
USERS = ["device-alpha-7f3e", "device-bravo-91aa", "device-charlie-0c2d"]


def _samples(text: str) -> dict[str, str]:
    return dict(line.split(" ", 1) for line in text.splitlines() if line and not line.startswith("#"))


def _assert_declared(text: str) -> None:
    families = {
        family["name"]: family
        for family in json.loads(MANIFEST.read_text(encoding="utf-8"))["families"]
    }
    for series in _samples(text):
        name = series.split("{", 1)[0]
        assert name in families, name
        assert set(re.findall(r'([a-z_]+)="', series)) == set(families[name]["labels"])


def _awg(tmp_path: Path, output: str, *, exit_code: int = 0) -> subprocess.CompletedProcess[str]:
    stub = tmp_path / "awg"
    (tmp_path / "awg.out").write_text(output, encoding="utf-8")
    stub.write_text(
        "#!/bin/sh\n"
        '[ "$*" = "show all latest-handshakes" ] || exit 64\n'
        f'cat "{tmp_path / "awg.out"}"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return subprocess.run(
        [sys.executable, str(AWG_EXPORTER), "--awg-bin", str(stub), "--fresh-window", "180",
         "--output", str(tmp_path / "vpn_awg.prom")],
        capture_output=True, text=True, timeout=10,
    )


def test_awg_exporter_publishes_only_fresh_and_total_counts(tmp_path: Path) -> None:
    now = int(time.time())
    fixture = (
        f"awg0\t{PEER_KEYS[0]}\t{now - 30}\n"
        f"awg0\t{PEER_KEYS[1]}\t{now - 3600}\n"
        f"awg1\t{PEER_KEYS[2]}\t{now - 5}\n"
    )

    result = _awg(tmp_path, fixture)

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "vpn_awg.prom").read_text(encoding="utf-8")
    samples = _samples(metrics)
    assert samples["vpn_awg_peers"] == "3"
    assert samples["vpn_awg_peers_fresh_handshake"] == "2"
    assert samples["vpn_awg_handshake_collection_success"] == "1"
    for private in (*PEER_KEYS, "awg0", "awg1"):
        assert private not in metrics
        assert private not in result.stdout + result.stderr
    _assert_declared(metrics)


def test_awg_exporter_counts_a_peer_that_never_completed_a_handshake_as_stale(tmp_path: Path) -> None:
    result = _awg(tmp_path, f"awg0\t{PEER_KEYS[0]}\t0\n")

    assert result.returncode == 0, result.stderr
    samples = _samples((tmp_path / "vpn_awg.prom").read_text(encoding="utf-8"))
    assert (samples["vpn_awg_peers"], samples["vpn_awg_peers_fresh_handshake"]) == ("1", "0")


@pytest.mark.parametrize(
    ("output", "exit_code"),
    [(f"awg0\t{PEER_KEYS[0]}\tnot-a-time\n", 0), (f"{PEER_KEYS[0]} leaked on failure\n", 1)],
    ids=["malformed", "tool-failure"],
)
def test_awg_exporter_reports_failure_without_peer_material(
    tmp_path: Path, output: str, exit_code: int
) -> None:
    result = _awg(tmp_path, output, exit_code=exit_code)

    assert result.returncode == 1
    metrics = (tmp_path / "vpn_awg.prom").read_text(encoding="utf-8")
    assert _samples(metrics)["vpn_awg_handshake_collection_success"] == "0"
    assert "vpn_awg_peers" not in metrics
    assert PEER_KEYS[0] not in metrics + result.stdout + result.stderr


class _TrafficApi(http.server.BaseHTTPRequestHandler):
    secret = "traffic-api-secret-fixture-0000000000000"
    documents = {
        "/traffic": {
            USERS[0]: {"tx": 100, "rx": 1000},
            USERS[1]: {"tx": 20, "rx": 300},
            USERS[2]: {"tx": 3, "rx": 40},
        },
        "/online": {USERS[0]: 2, USERS[1]: 1},
    }

    def do_GET(self) -> None:
        if self.headers.get("Authorization") != self.secret or self.path not in self.documents:
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(self.documents[self.path]).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def traffic_api():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _TrafficApi)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _hysteria(tmp_path: Path, listen: str, secret: str = _TrafficApi.secret) -> subprocess.CompletedProcess[str]:
    secret_file = tmp_path / "secret"
    secret_file.write_text(secret + "\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(HYSTERIA_EXPORTER), "--listen", listen, "--secret-file", str(secret_file),
         "--output", str(tmp_path / "vpn_hysteria.prom"), "--timeout", "5"],
        capture_output=True, text=True, timeout=15,
    )


def test_hysteria_exporter_sums_traffic_without_user_identifiers(tmp_path: Path, traffic_api: str) -> None:
    result = _hysteria(tmp_path, traffic_api)

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "vpn_hysteria.prom").read_text(encoding="utf-8")
    samples = _samples(metrics)
    assert samples["vpn_hysteria_transmit_bytes_total"] == "123"
    assert samples["vpn_hysteria_receive_bytes_total"] == "1340"
    assert samples["vpn_hysteria_online_connections"] == "3"
    assert samples["vpn_hysteria_traffic_collection_success"] == "1"
    for private in (*USERS, _TrafficApi.secret):
        assert private not in metrics + result.stdout + result.stderr
    _assert_declared(metrics)


@pytest.mark.parametrize("case", ["api-down", "wrong-secret", "public-listener"])
def test_hysteria_exporter_reports_failure_metric(tmp_path: Path, traffic_api: str, case: str) -> None:
    if case == "api-down":
        result = _hysteria(tmp_path, "127.0.0.1:9")
    elif case == "wrong-secret":
        result = _hysteria(tmp_path, traffic_api, secret="not-the-secret")
    else:
        result = _hysteria(tmp_path, "0.0.0.0:" + traffic_api.rsplit(":", 1)[1])

    assert result.returncode == 1
    metrics = (tmp_path / "vpn_hysteria.prom").read_text(encoding="utf-8")
    assert _samples(metrics)["vpn_hysteria_traffic_collection_success"] == "0"
    assert "vpn_hysteria_transmit_bytes_total" not in metrics
    assert _TrafficApi.secret not in result.stderr


def test_awg_exporter_unit_writes_no_core_dump() -> None:
    from scripts.template_render import merge_render_vars, render_template

    # The root process holds CAP_NET_ADMIN on the device socket; a core file would keep its memory on disk.
    unit = render_template(ROOT / "ansible/roles/amneziawg/templates/awg-handshake-exporter.service.j2", merge_render_vars())
    assert "LimitCORE=0" in unit.splitlines()


def test_hysteria_exporter_unit_runs_unprivileged_with_the_hardening_floor() -> None:
    from scripts.template_render import merge_render_vars, render_template

    unit = render_template(ROOT / "ansible/roles/hysteria/templates/hysteria-traffic-exporter.service.j2", merge_render_vars())
    directives = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in unit.splitlines() if "=" in line and not line.startswith("#")}
    assert directives["User"] == directives["Group"] == "vpn-hysteria-exporter"
    assert directives["SupplementaryGroups"] == "node_exporter_textfile"
    assert directives["CapabilityBoundingSet"] == "" and directives["NoNewPrivileges"] == "true"
    for name, value in (("MemoryDenyWriteExecute", "true"), ("ProtectProc", "invisible"), ("ProcSubset", "pid"),
                        ("RestrictAddressFamilies", "AF_INET"), ("SystemCallArchitectures", "native"),
                        ("UMask", "0027"), ("LimitCORE", "0")):
        assert directives[name] == value, name
    filters = [line.split("=", 1)[1] for line in unit.splitlines() if line.startswith("SystemCallFilter=")]
    assert filters == ["@system-service", "~@privileged @resources"]
    assert "LoadCredential=hysteria-traffic-secret:" in unit
