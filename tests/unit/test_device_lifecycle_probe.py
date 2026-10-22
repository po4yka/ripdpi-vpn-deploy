"""Portable contract, actual TLS traffic and bounded subprocess coverage."""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import select
import shutil
import socket
import ssl
import sys
import threading

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import device_lifecycle_probe as renderer
import device_lifecycle_probe_worker as worker
from device_lifecycle_credentials import issue, profile
from test_awg_device_binding import document as awg_document
from transport_semantics import transport_errors, xhttp_endpoints


def authority():
    value = awg_document()
    value.update(xray={"clients": [{"name": "device0", "uuid": "00d9c096-7ff5-4fb2-aead-b4a6cba22bbd", "short_id": "aabbccdd"}],
                       "server_names": ["localhost"], "reality_public_key": "a" * 43},
                 nginx_xhttp={"server_name": "localhost", "fallback_enabled": True},
                 hysteria={"clients": [{"name": "device0", "password": "private-hy-password"}], "server_name": "localhost",
                           "bandwidth_up": "100 mbps", "bandwidth_down": "200 mbps"},
                 snell_secrets={"variants": [{"id": name, "psk": "STUB_SHARED_VARIANT_KEY", "users": [{"name": "device0", "userkey": "STUB_DEVICE_USER_KEY"}]}
                                             for name in ("v4-stream", "v6-default", "v6-unshaped")]},
                 naive_secrets={"server_name": "localhost", "clients": [{"name": "device0", "username": "private-user", "password": "private-pass"}]})
    return value


def settings():
    value = renderer.context("")
    value["vpn"].update(enable_xray_reality=True, enable_nginx_xhttp=True, enable_hysteria=True,
                        enable_amneziawg=True, enable_snell=True, enable_naive=True)
    return value


def test_renderer_all_variants_exact_device_and_no_source_mutation(monkeypatch):
    source = authority()
    source["xray"]["cohorts"] = [
        {"name": "vision", "clients": ["device0"], "port": 443, "flow_mode": "vision"},
        {"name": "mux", "clients": ["device0"], "port": 2053, "flow_mode": "mux", "finalmask": True}]
    original = copy.deepcopy(source)
    config = settings()
    monkeypatch.setattr(renderer, "context", lambda _: copy.deepcopy(config))
    result = renderer.render_profiles(source, "", "device0", "upcloud:fixture", "192.0.2.10")
    assert source == original
    assert len(result) == 13
    xray = [row for row in result if row["engine"] == "xray"]
    assert len(xray) == 4
    first, second = (row["config"]["outbounds"][0] for row in xray[:2])
    assert first["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
    assert "flow" not in second["settings"]["vnext"][0]["users"][0]
    assert second["mux"] == {"enabled": True, "concurrency": 8}
    assert second["streamSettings"]["finalmask"]["tcp"][0]["type"] == "sudoku"
    assert {row["config"]["outbounds"][0]["settings"]["vnext"][0]["port"] for row in xray[2:]} == {8443, 2083}
    snell = [row for row in result if row["engine"] == "snell"]
    assert len(snell) == 6 and {row["config"]["outbounds"][0]["reuse"] for row in snell} == {False, True}
    awg = next(row for row in result if row["engine"] == "awg")
    assert "<CLIENT_PRIVATE_KEY>" not in awg["config"]["text"]
    assert original["client_registry"]["device0"]["awg_private_key"] in awg["config"]["text"]
    assert awg["witness"]["instance"] == "awg0"
    assert "device0" not in " ".join(row["id"] for row in result)
    worker.validate_request(request(result, "https://localhost/probe"))


def test_renderer_missing_identity_and_mismatched_awg_recovery_refuse(monkeypatch):
    config = settings()
    monkeypatch.setattr(renderer, "context", lambda _: copy.deepcopy(config))
    source = authority()
    source["hysteria"]["clients"] = []
    with pytest.raises(ValueError, match="probe-client"):
        renderer.render_profiles(source, "", "device0", "upcloud:fixture", "192.0.2.10")
    source = authority()
    source["client_registry"]["device0"]["awg_private_key"] = source["client_registry"]["device1"]["awg_private_key"]
    with pytest.raises(ValueError, match="key-mismatch"):
        renderer.render_profiles(source, "", "device0", "upcloud:fixture", "192.0.2.10")


def test_retained_disabled_authorities_and_migrated_registry_are_still_probed(monkeypatch):
    config = settings()
    config["vpn"] = {name: False for name in config["vpn"]}
    monkeypatch.setattr(renderer, "context", lambda _: copy.deepcopy(config))
    source = authority()
    source["client_registry"]["device0"]["awg_binding"] = {"provider": "upcloud", "environment": "replacement", "instance": "awg4"}
    before = copy.deepcopy(source)
    with pytest.raises(ValueError, match="no-device-probe-profiles"):
        renderer.render_profiles(source, "", "device0", "upcloud:fixture", "192.0.2.10")
    profiles = renderer.render_profiles(source, "", "device0", "upcloud:fixture", "192.0.2.10", include_disabled=True)
    assert {row["engine"] for row in profiles} == worker.ENGINES
    assert next(row for row in profiles if row["engine"] == "awg")["witness"]["instance"] == "awg0"
    assert source == before
    source["amneziawg_secrets"]["instances"][1]["peers"][0]["name"] = "device0"
    with pytest.raises(ValueError, match="ambiguous-probe-awg-peer"):
        renderer.render_profiles(source, "", "device0", "upcloud:fixture", "192.0.2.10", include_disabled=True)


@pytest.mark.parametrize("retained_xhttp", [False, True])
def test_actual_p0_only_issue_and_revoke_render_only_known_endpoint_authority(retained_xhttp):
    source = yaml.safe_load((Path(__file__).resolve().parents[2] / "tests/fixtures/secrets-sample.yml").read_text())
    frontend = source["nginx_xhttp"]
    for section in ("nginx_xhttp", "hysteria", "amneziawg_secrets", "snell_secrets", "naive_secrets"):
        source.pop(section, None)
    source["client_registry"] = {}
    resolved = profile("p0-minimal")
    assert transport_errors(source, resolved) == []
    source = issue({"upcloud:fixture": source}, {"upcloud:fixture": {"cohort": "p0-minimal"}},
                   "device0", ["upcloud:fixture"], "2026-10-22T00:00:00Z")["upcloud:fixture"]
    issued = renderer.render_profiles(source, "p0-minimal", "device0", "upcloud:fixture", "192.0.2.10")
    assert issued and all(row["config"]["outbounds"][0]["streamSettings"]["network"] == "raw" for row in issued)
    if retained_xhttp:
        source["nginx_xhttp"] = frontend
    before = copy.deepcopy(source)
    revoked = renderer.render_profiles(source, "p0-minimal", "device0", "upcloud:fixture", "192.0.2.10", include_disabled=True)
    assert source == before and revoked[:len(issued)] == issued
    xhttp = [row["config"]["outbounds"][0] for row in revoked if row["config"]["outbounds"][0]["streamSettings"]["network"] == "xhttp"]
    expected = xhttp_endpoints(source, resolved) if retained_xhttp else []
    assert [(row["settings"]["vnext"][0]["port"], row["streamSettings"]["tlsSettings"]["serverName"]) for row in xhttp] == [
        (endpoint["port"], endpoint["host"]) for endpoint in expected]
    worker.validate_request(request(revoked, "https://localhost/probe"))


def certificate(directory):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "owned probe")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                                                       x509.IPAddress(ipaddress.ip_address("10.70.0.1")),
                                                       x509.IPAddress(ipaddress.ip_address("203.0.113.239"))]), False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = directory / "cert.pem", directory / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    return cert_path, key_path


class HttpsOrigin:
    body = b"owned exact lifecycle payload\n"

    def __init__(self, certificate_path, key_path, *, address="127.0.0.1"):
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(owner.body)))
                self.end_headers()
                self.wfile.write(owner.body)
            def log_message(self, *_):
                pass
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols(["h2", "http/1.1"])
        context.load_cert_chain(certificate_path, key_path)

        class Server(http.server.ThreadingHTTPServer):
            daemon_threads = False

            def finish_request(self, connection, address):
                connection.settimeout(2)
                try:
                    secured = context.wrap_socket(connection, server_side=True)
                except (OSError, ssl.SSLError):
                    return
                with secured:
                    super().finish_request(secured, address)

        self.server = Server((address, 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"https://{address}:{self.server.server_port}/probe"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        assert not self.thread.is_alive()


class TlsConnectFixture:
    """Portable real TLS CONNECT fixture, explicitly not native Naive proof."""
    def __init__(self, cert_path, key_path):
        owner = self
        self.allowed = True
        self.tunnels = 0
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_CONNECT(self):
                auth = "Basic " + base64.b64encode(b"private-user:private-pass").decode()
                if not owner.allowed or self.headers.get("Proxy-Authorization") != auth:
                    self.send_error(407)
                    return
                host, port = self.path.rsplit(":", 1)
                with socket.create_connection((host, int(port)), timeout=3) as destination:
                    owner.tunnels += 1
                    self.send_response(200)
                    self.end_headers()
                    peers = [self.connection, destination]
                    while True:
                        readable, _, _ = select.select(peers, [], [], 3)
                        if not readable:
                            return
                        for current in readable:
                            data = current.recv(16384)
                            if not data:
                                return
                            (destination if current is self.connection else self.connection).sendall(data)
            def log_message(self, *_):
                pass
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert_path, key_path)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        assert not self.thread.is_alive()


def test_https_control_remains_available_during_stalled_tls_handshake(tmp_path, monkeypatch):
    cert, key = certificate(tmp_path)
    origin = HttpsOrigin(cert, key)
    accepted = threading.Event()
    get_request = origin.server.get_request

    def accept_connection():
        accepted.set()
        return get_request()

    monkeypatch.setattr(origin.server, "get_request", accept_connection)
    try:
        with socket.create_connection(("127.0.0.1", origin.server.server_port), timeout=1) as stalled:
            assert accepted.wait(1), "the owned idle connection must reach the listener"
            runtime = PortableRuntime(binaries={"curl": shutil.which("curl")}, ca_file=cert)
            measured = runtime.http(request([], origin.url)["control"], 1, tmp_path)
            assert measured["accepted"], measured
            stalled.settimeout(3)
            assert stalled.recv(1) == b"", "the unfinished TLS handshake must expire"
    finally:
        origin.close()


def request(profiles, url):
    return {"schema_version": 1, "mode": "accept", "profiles": profiles,
            "control": {"url": url, "status": 200, "body_sha256": hashlib.sha256(HttpsOrigin.body).hexdigest()},
            "timeout_seconds": 2}


class PortableRuntime(worker.Runtime):
    def binary(self, name):
        # macOS system binaries are root-owned; the production root/ancestor
        # admission is tested separately and remains enabled in native cases.
        return self.binaries[name]


def service_fixture(directory):
    path = directory / "service-state"
    path.write_text("#!/bin/sh\nprintf 'LoadState=loaded\\nActiveState=active\\nSubState=running\\nMainPID=1\\n'\n")
    path.chmod(0o700)
    return str(path)


def naive_profile(directory, port):
    path = directory / "runtime.json"
    credential = "private-user:private-pass"
    encoded = base64.b64encode(base64.b64encode(credential.encode())).decode()
    path.write_text(json.dumps({"apps": {"http": {"servers": {"test": {"handler": "forward_proxy", "auth_credentials": [encoded]}}}}}))
    path.chmod(0o600)
    return {"id": "naive-1", "engine": "naive", "config": {"address": "127.0.0.1", "port": port,
            "server_name": "localhost", "username": "private-user", "password": "private-pass"},
            "witness": {"kind": "basic", "credential": credential, "instance": None,
                        "config_path": str(path), "unit": "owned.service"}}


@pytest.mark.parametrize("servers", [None, [], "invalid", 1])
def test_naive_witness_refuses_malformed_server_tree(tmp_path, servers):
    profile = naive_profile(tmp_path, 12345)
    Path(profile["witness"]["config_path"]).write_text(json.dumps({"apps": {"http": {"servers": servers}}}))
    runtime = PortableRuntime(binaries={"systemctl": service_fixture(tmp_path)})
    with pytest.raises(worker.ProbeError, match="runtime-authority-invalid"):
        runtime.witness(profile)


def test_real_https_control_and_tls_connect_receipt_is_exact_and_private(tmp_path):
    cert, key = certificate(tmp_path)
    origin, proxy = HttpsOrigin(cert, key), TlsConnectFixture(cert, key)
    try:
        profile = naive_profile(tmp_path, proxy.server.server_port)
        runtime = PortableRuntime(binaries={"curl": shutil.which("curl"), "systemctl": service_fixture(tmp_path)}, ca_file=cert)
        value = request([profile], origin.url)
        accepted = worker.run_request(value, runtime=runtime)
        assert accepted["profiles"][0]["state"] == "accepted", accepted
        assert proxy.tunnels == 1 and accepted["cleanup"] == "confirmed"
        assert "private-" not in json.dumps(accepted) and origin.url not in json.dumps(accepted)
        proxy.allowed = False
        Path(profile["witness"]["config_path"]).write_text('{"apps":{"http":{"servers":{}}}}')
        value["mode"] = "deny"
        denied = worker.run_request(value, runtime=runtime)
        assert denied["profiles"][0]["state"] == "denied", denied
        assert denied["profiles"][0]["peer_absent"] and denied["profiles"][0]["control_ok"]
        assert proxy.tunnels == 1
        value["control"]["body_sha256"] = "0" * 64
        unknown = worker.run_request(value, runtime=runtime)
        assert unknown["profiles"][0]["state"] == "unknown" and unknown["control"] == "failed"
    finally:
        proxy.close()
        origin.close()


@pytest.mark.parametrize("mutation", ["redirect", "userinfo", "extra", "duplicate", "witness", "budget"])
def test_untrusted_request_cannot_expand_probe_authority(tmp_path, mutation):
    value = request([naive_profile(tmp_path, 12345)], "https://localhost/probe")
    if mutation == "redirect":
        value["control"]["status"] = 302
    elif mutation == "userinfo":
        value["control"]["url"] = "https://user:secret@localhost/probe"
    elif mutation == "extra":
        value["command"] = ["unrelated"]
    elif mutation == "duplicate":
        value["profiles"] *= 2
    elif mutation == "witness":
        value["profiles"][0]["witness"]["config_path"] = "/etc/../private"
    else:
        value["timeout_seconds"] = 31
    with pytest.raises(worker.ProbeError):
        worker.validate_request(value)


def test_command_timeout_reclaims_actual_child(tmp_path):
    pid = tmp_path / "pid"
    script = "import os,time,pathlib; pathlib.Path(__import__('sys').argv[1]).write_text(str(os.getpid())); time.sleep(60)"
    runtime = PortableRuntime()
    with pytest.raises(worker.ProbeError, match="runtime-command-timeout"):
        runtime.command([sys.executable, "-c", script, str(pid)], timeout=0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid.read_text()), 0)


def test_missing_tools_do_not_become_denial(tmp_path):
    runtime = worker.Runtime(binaries={"curl": str(tmp_path / "missing")})
    value = request([naive_profile(tmp_path, 12345)], "https://localhost/probe")
    value["mode"] = "deny"
    result = worker.run_request(value, runtime=runtime)
    assert result["profiles"][0]["state"] == "unknown"
    assert not result["profiles"][0]["control_ok"]


@pytest.mark.parametrize("case", [
    "retired", "active", "peer-present", "short-timeout", "other-engine",
    "initial-control-failed", "final-control-failed", "setup-incomplete",
    "cleanup-incomplete", "runtime-unhealthy", "changed-authority", "changed-unit",
    "inactive-only-before", "inactive-only-after", "absent-only-before",
    "absent-only-after", "missing-duration", "different-exit",
])
def test_hysteria_retirement_requires_complete_stable_timeout_evidence(case):
    """Classifier boundaries only; native traffic is verified separately."""
    before = {"peer_absent": True, "runtime_healthy": True, "inactive_confirmed": True,
              "token": "absent", "unit_token": "stopped"}
    after = before.copy()
    measured = {"accepted": False, "exit": 28, "elapsed": 2.0,
                "setup_ok": True, "cleanup_ok": True}
    controls = [True, True]
    if case == "active":
        before["inactive_confirmed"] = after["inactive_confirmed"] = False
    elif case == "peer-present":
        before["peer_absent"] = after["peer_absent"] = False
    elif case == "short-timeout":
        measured["elapsed"] = 1.999
    elif case == "initial-control-failed":
        controls[0] = False
    elif case == "final-control-failed":
        controls[1] = False
    elif case == "setup-incomplete":
        measured["setup_ok"] = False
    elif case == "cleanup-incomplete":
        measured["cleanup_ok"] = False
    elif case == "runtime-unhealthy":
        before["runtime_healthy"] = after["runtime_healthy"] = False
    elif case == "changed-authority":
        after["token"] = "changed"
    elif case == "changed-unit":
        after["unit_token"] = "changed"
    elif case == "inactive-only-before":
        after["inactive_confirmed"] = False
    elif case == "inactive-only-after":
        before["inactive_confirmed"] = False
    elif case == "absent-only-before":
        after["peer_absent"] = False
    elif case == "absent-only-after":
        before["peer_absent"] = False
    elif case == "missing-duration":
        del measured["elapsed"]
    elif case == "different-exit":
        measured["exit"] = 18
    witness_results, control_results = iter((before, after)), iter(controls)

    class Runtime(worker.Runtime):
        def http(self, *_args, **_kwargs):
            return {"accepted": next(control_results)}

        def witness(self, _profile):
            return next(witness_results)

        def stream(self, *_args):
            return measured

    engine = "xray" if case == "other-engine" else "hysteria"
    profile = {"id": engine + "-1", "engine": engine, "config": {}, "witness": {
        "kind": "uuid" if engine == "xray" else "username", "credential": "owned-user",
        "instance": None, "config_path": "/etc/owned/config", "unit": "owned.service"}}
    value = request([profile], "https://localhost/probe")
    value["mode"] = "deny"
    row = worker.run_request(value, runtime=Runtime())["profiles"][0]
    assert row["state"] == ("denied" if case == "retired" else "unknown"), row
    if case == "retired":
        assert row["reason"] == "retired-runtime-access-failed"
