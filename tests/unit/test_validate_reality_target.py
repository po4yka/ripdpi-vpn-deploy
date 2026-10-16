"""Actual local TLS identities and finite process ownership; no private targets."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading
import time

import pytest

from reality_target_validation import names, endpoint, validate, execute, ValidationError


@pytest.mark.parametrize("raw,expected", [
    ("EXACT.example.test., alpha.example.test exact.example.test", ["exact.example.test", "alpha.example.test"]),
    ("a.example.test,b.example.test", ["a.example.test", "b.example.test"]),
])
def test_name_normalization(raw, expected):
    assert names(raw) == expected


@pytest.mark.parametrize("raw", ["", " , ", "*.example.test", "a..example.test", "a.example.test/", "a\x00.example.test", "a.example.test,,b.example.test", "a.example.test,", "a.example.test.."])
def test_invalid_names_refuse_before_network(raw):
    with pytest.raises(ValidationError):
        names(raw)


@contextmanager
def tls_peer(tmp_path, san="DNS:*.example.test,DNS:exact.other.test"):
    certificate, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=not-a-SAN.example.test",
        "-addext", "subjectAltName=" + san, "-days", "1"], check=True, capture_output=True, timeout=10)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"owned local target")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(certificate, key)
    context.set_alpn_protocols(["h2", "http/1.1"])
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server.server_port, str(certificate)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        assert not thread.is_alive()


def test_real_exact_and_single_wildcard_identity_and_redacted_claims(tmp_path):
    with tls_peer(tmp_path) as (port, ca):
        report = validate(f"127.0.0.1:{port}", "EXACT.other.test.,alpha.example.test", budget=10, stage=3, ca=ca)
    assert report["verdict"] == "passed"
    assert len(report["observations"]) == 2
    assert report["browser_clienthello"] == report["filtered_survival"] == "unverified"
    assert "example.test" not in json.dumps(report) and "127.0.0.1" not in json.dumps(report)


@pytest.mark.parametrize("case", ["deep-wildcard", "wrong-san", "untrusted"])
def test_real_tls_identity_or_trust_failure_preserves_authority(tmp_path, case):
    with tls_peer(tmp_path) as (port, ca):
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        name = "deep.alpha.example.test" if case == "deep-wildcard" else "wrong.other.test" if case == "wrong-san" else "alpha.example.test"
        report = validate(f"127.0.0.1:{port}", name, budget=5, stage=2, ca=None if case == "untrusted" else ca)
        assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert report["verdict"] == "failed"


def test_owned_mode_never_uses_local_target_as_public_service():
    with pytest.raises(ValidationError, match="owned-public-endpoint-required"):
        validate("127.0.0.1:443", "owned.example.test", mode="owned-public")
    with pytest.raises(ValidationError, match="owned-public-path-required"):
        validate("127.0.0.1:443", "owned.example.test", mode="owned-public", public_endpoint="127.0.0.1:443")


def test_stalled_tls_terminates_within_aggregate_budget():
    with socket.socket() as peer:
        peer.bind(("127.0.0.1", 0)); peer.listen()
        start = time.monotonic()
        report = validate(f"127.0.0.1:{peer.getsockname()[1]}", "a.example.test,b.example.test", budget=1, stage=.5)
    assert report["verdict"] == "failed"
    assert time.monotonic() - start < 2.5


def test_stage_deadline_reclaims_actual_descendant(tmp_path):
    marker = tmp_path / "child.pid"
    # Fork within the admitted interpreter so this tests descendant ownership,
    # rather than racing a second interpreter's startup against the deadline.
    parent = ("import os,time\nif os.fork()==0:\n with open(" + repr(str(marker))
              + ",'w') as stream: stream.write(str(os.getpid()))\ntime.sleep(60)\n")
    with pytest.raises(ValidationError):
        execute([sys.executable, "-c", parent], time.monotonic() + .5, .5)
    pid = int(marker.read_text())
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, timeout=3)
    assert result.returncode != 0 or result.stdout.strip().startswith("Z")


def test_wrapper_emits_only_redacted_error_without_implicit_private_input(tmp_path):
    environment = {**os.environ, "TARGET": "invalid-private-marker:0", "SERVER_NAMES": "private-marker.example.test"}
    result = subprocess.run(["bash", str(Path(__file__).resolve().parents[2] / "scripts/validate-reality-target.sh")],
        env=environment, text=True, capture_output=True, timeout=5)
    assert result.returncode == 1
    assert "private-marker" not in result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "failed"


def test_explicit_empty_names_never_fall_back_to_operator_secrets(monkeypatch, capsys):
    import client_payload
    import reality_target_validation
    monkeypatch.setenv("TARGET", "127.0.0.1:443")
    monkeypatch.setenv("SERVER_NAMES", "")
    monkeypatch.setattr(sys, "argv", ["reality_target_validation.py"])
    monkeypatch.setattr(client_payload, "read_document", lambda *a, **kw: pytest.fail("explicit input read operator authority"))
    assert reality_target_validation.main() == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "failed"


def test_dns_worker_refuses_overflow_instead_of_hiding_additional_addresses(monkeypatch, capsys):
    import io
    from types import SimpleNamespace
    import reality_target_validation as module
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (f"192.0.2.{i}", 443)) for i in range(1, 10)]
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args, **kwargs: answers)
    monkeypatch.setattr(module.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b'{"host":"owned.example","port":443}')))
    with pytest.raises(ValidationError, match="dns-empty-or-unbounded"):
        module.worker("dns")
    assert not capsys.readouterr().out


def test_dns_worker_retains_all_eight_unique_candidates_with_duplicate_answers(monkeypatch, capsys):
    import io
    from types import SimpleNamespace
    import reality_target_validation as module
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (f"192.0.2.{i}", 443)) for i in range(1, 9)]
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args, **kwargs: answers + answers[:1])
    monkeypatch.setattr(module.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b'{"host":"owned.example","port":443}')))
    module.worker("dns")
    assert json.loads(capsys.readouterr().out) == [f"192.0.2.{i}" for i in range(1, 9)]


@pytest.mark.parametrize("explicit", [{"TARGET": ""}, {"SERVER_NAMES": ""}, {"SERVER_NAMES": "bad/name"}])
def test_invalid_partial_explicit_inputs_refuse_before_loading_operator_authority(monkeypatch, capsys, explicit):
    import client_payload
    import reality_target_validation
    for name in ("TARGET", "SERVER_NAMES"):
        monkeypatch.delenv(name, raising=False)
    for name, value in explicit.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["reality_target_validation.py"])
    monkeypatch.setattr(client_payload, "read_document", lambda *a, **kw: pytest.fail("invalid explicit input read operator authority"))
    assert reality_target_validation.main() == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "failed"


@pytest.mark.parametrize("public_endpoint", [None, "", "bad/path"])
def test_owned_public_prerequisite_refuses_before_loading_operator_authority(monkeypatch, capsys, public_endpoint):
    import client_payload
    import reality_target_validation
    for name in ("TARGET", "SERVER_NAMES", "REALITY_TARGET_PUBLIC_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    if public_endpoint is not None:
        monkeypatch.setenv("REALITY_TARGET_PUBLIC_ENDPOINT", public_endpoint)
    monkeypatch.setattr(sys, "argv", ["reality_target_validation.py", "--mode", "owned-public"])
    monkeypatch.setattr(client_payload, "read_document", lambda *a, **kw: pytest.fail("invalid public endpoint read operator authority"))
    assert reality_target_validation.main() == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "failed"
