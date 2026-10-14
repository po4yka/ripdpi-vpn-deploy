"""Real pinned clients, peer attribution and owned HTTPS origin/rollback proof."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
import yaml

from liveness_profiles import build_profiles

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime
spec = importlib.util.spec_from_file_location(
    "xhttp_owned_native_fixture", ROOT / "tests/integration/transport_destination_boundary/fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def get(stack, port, path):
    deadline = time.monotonic() + 10
    while True:
        result = subprocess.run([
            "ip", "netns", "exec", stack.namespace, "curl", "--silent", "--show-error",
            "--noproxy", "*", "--max-time", "5", "--cacert", str(stack.cert),
            "--resolve", f"owned.example:{port}:192.0.2.90", "-D", "-",
            f"https://owned.example:{port}{path}",
        ], text=True, capture_output=True, timeout=8)
        if result.returncode == 7 and time.monotonic() < deadline:
            time.sleep(.1)
            continue
        assert result.returncode == 0, "owned HTTPS request failed"
        return result.stdout


def publish(stack, *, invalid=False):
    def row(path, body, mode):
        return {"path": str(path), "kind": "file", "content_b64": base64.b64encode(body).decode(),
                "mode": mode, "uid": 0, "gid": 0}
    document = {
        "owner": "xhttp-endpoint", "roots": [str(stack.ingress)],
        "files": [row(stack.nginx_config, stack.nginx_config.read_bytes(), "0600"),
                  row(stack.ingress / "certificate.pem", (stack.ingress / "certificate.pem").read_bytes(), "0644"),
                  row(stack.ingress / "private.pem", b"invalid candidate key" if invalid else
                      (stack.ingress / "private.pem").read_bytes(), "0600")],
        "validate_argv": [shutil.which("nginx"), "-t", "-c", str(stack.nginx_config), "-p", str(stack.library)],
        "unit": stack.token + "-nginx.service", "activation": "reload", "check": False,
        "credential_root": "", "runtime_directories": [], "activate_inactive": False,
        "desired_enabled": None,
    }
    return subprocess.run([
        sys.executable, str(ROOT / "ansible/roles/nginx-xhttp/files/nginx_transaction.py"),
    ], input=json.dumps(document), capture_output=True, text=True, timeout=70)


def exported_outbound(stack):
    """Synthetic provider metadata is input only; emission and client execution are real."""
    profile = ROOT / "ansible/group_vars" / ("vpn-" + stack.token + ".yml")
    metadata = ROOT / "tests/fixtures/tf-output-sample.json"
    previous = metadata.read_bytes()
    assert not profile.exists()
    document = {name: stack.values[name] for name in ("xray", "nginx_xhttp", "hysteria", "transport_egress_secrets")}
    document["client_registry"] = {"native-device": {"status": "active"}}
    private = stack.file("emission.yaml", yaml.safe_dump(document))
    try:
        profile.write_text(yaml.safe_dump({
            "vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": True, "enable_hysteria": False,
                    "enable_amneziawg": False, "enable_snell": False, "enable_naive": False},
            "nginx_xhttp_public_port": stack.values["nginx_xhttp_public_port"],
        }))
        selected = json.loads(previous)
        selected["server_ipv4"]["value"] = "192.0.2.90"
        metadata.write_text(json.dumps(selected))
        environment = {key: value for key, value in os.environ.items() if key not in {
            "VPN_SECRETS_FILE", "SOPS_FILES", "SOPS_FILE", "HOSTS", "COHORTS", "PROVIDER", "ENV"}}
        environment.update(VPN_SECRETS_FILE=str(private), HOSTS="upcloud:fixture", COHORTS=stack.token,
                           PATH=str(ROOT / "tests/stubs/bin") + ":" + environment["PATH"])
        unsupported = subprocess.run(["bash", str(ROOT / "scripts/emit-singbox.sh"), "native-device",
                                      "--profile-format", "sing-box"], env=environment,
                                     capture_output=True, text=True, timeout=30)
        assert unsupported.returncode != 0 and not unsupported.stdout
        assert stack.uuid not in unsupported.stderr
        result = subprocess.run(["bash", str(ROOT / "scripts/emit-singbox.sh"), "native-device",
                                 "--profile-format", "ripdpi"], env=environment, capture_output=True,
                                text=True, timeout=30)
        assert result.returncode == 0, "canonical selected-client emission failed"
        emitted = json.loads(result.stdout)
        def no_key(_):
            raise AssertionError("unused AWG material was requested")
        profiles = build_profiles(None, emitted, document, "native-device", ["p1-xhttp"], None,
                                  None, None, no_key, str(stack.library), awg_defaults={}, awg_cohort={})
        outbound = profiles["files"]["xray.json"]["outbounds"][0]
        server = outbound["settings"]["vnext"][0]
        assert server["address"] == "192.0.2.90" and server["port"] == stack.values["nginx_xhttp_public_port"]
        assert server["users"] == [{"id": stack.uuid, "encryption": "none"}]
        return outbound
    finally:
        metadata.write_bytes(previous)
        profile.unlink(missing_ok=True)


@pytest.mark.parametrize("primary_port", [443, 8443])
def test_pinned_endpoints_preserve_peer_origin_privacy_and_rejected_candidate(primary_port):
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    for binary in ("xray", "hysteria", "nginx", "curl", "ip", "systemctl", "openssl"):
        assert shutil.which(binary), "native endpoint prerequisite is unavailable"
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    for binary in ("xray", "hysteria"):
        assert pins[binary]["version"].lstrip("v") in fixture.command([binary, "version"])
    stack = fixture.NativeStack()
    publication = Path("/var/lib/vpn-nginx-publication") / (stack.token + "-nginx.service")
    assert not publication.exists()
    global_hosts = Path("/etc/hosts").read_bytes()
    try:
        stack.start()
        stack.start_frontend("p1", primary_port=primary_port, path="/native-sync/packet-v2", fallback=True)
        origin = "https://owned.example" + ("" if primary_port == 443 else f":{primary_port}")
        for port in (primary_port, 2083):
            page = get(stack, port, "/")
            assert re.search(r"HTTP/(?:1\.1|2) 200\b", page) and f'content="{origin}/"' in page
            assert "application/atom+xml" in get(stack, port, "/feed.xml")
            assert f"{origin}/" in get(stack, port, "/sitemap.xml")
            assert f"Sitemap: {origin}/sitemap.xml" in get(stack, port, "/robots.txt")
        redirected = fixture.command([
            "ip", "netns", "exec", stack.namespace, "curl", "--silent", "--noproxy", "*",
            "--max-time", "5", "--resolve", "owned.example:80:192.0.2.90", "-I", "http://owned.example/",
        ])
        assert f"Location: {origin}/" in redirected
        exported = exported_outbound(stack)
        access = stack.library / "logs/access.log"
        for port in (primary_port, 2083):
            for supplied in (False, True):
                before = access.stat().st_size
                headers = {"X-Forwarded-For": "198.51.100.201, 198.51.100.202",
                           "X-Real-IP": "198.51.100.203", "Forwarded": "for=198.51.100.204"} if supplied else None
                client = stack.start_client("p1", endpoint_port=port, headers=headers, source_address="192.0.2.81",
                                            outbound=exported if port == primary_port else None)
                time.sleep(.5)
                stack.run_driver(client)
                observed = access.read_text()[before:]
                accepted = [line for line in observed.splitlines() if "vless-xhttp-localhost" in line and "accepted" in line]
                assert accepted and all("192.0.2.81:0" in line for line in accepted), "actual peer attribution differs"
                assert not any(f"198.51.100.{suffix}" in observed for suffix in range(201, 205))
        rejected_client = stack.start_client("p1", True, source_address="192.0.2.81")
        time.sleep(.5)
        stack.run_driver(rejected_client, True)
        adopted = publish(stack)
        assert adopted.returncode == 0, "complete endpoint adoption failed"
        before = {str(path): path.read_bytes() for path in stack.ingress.rglob("*") if path.is_file()}
        rejected = publish(stack, invalid=True)
        assert rejected.returncode != 0 and "nginx publication failed" in rejected.stderr
        assert before == {str(path): path.read_bytes() for path in stack.ingress.rglob("*") if path.is_file()}
        stack.run_driver(client)
        assert re.search(r"HTTP/(?:1\.1|2) 200\b", get(stack, primary_port, "/"))
        # An actual unauthenticated QUIC exchange invokes Hysteria's owned proxy.
        # It must reach the verified primary HTTPS listener and keep ordinary 404 semantics.
        hosts = stack.file("masquerade-hosts", "127.0.0.1 localhost\n192.0.2.90 owned.example\n", "h")
        stack.start_hysteria(masquerade_origin=origin, hosts=hosts)
        stack.start_client("hysteria", True)
        deadline = time.monotonic() + 10
        public_log = stack.library / "vpn-xhttp.access.log"
        while time.monotonic() < deadline:
            content = public_log.read_text() if public_log.exists() else ""
            if re.search(r'"POST /auth HTTP/(?:1\.1|2\.0)" 404\b', content):
                break
            time.sleep(.1)
        else:
            pytest.fail("native Hysteria masquerade did not reach the served HTTPS origin")
        assert Path("/etc/hosts").read_bytes() == global_hosts
        ordinary = "\n".join(path.read_text(errors="replace") for path in stack.library.glob("vpn-xhttp*.log"))
        assert stack.values["xray"]["xhttp_path"] not in ordinary and stack.uuid not in ordinary
        assert stack.hys_password not in ordinary
    finally:
        stack.close()
        if publication.exists():
            shutil.rmtree(publication)
