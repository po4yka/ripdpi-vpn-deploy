"""Exercise the real credential-aware sender against bounded local endpoints."""

from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs

import pytest

ROOT = Path(__file__).resolve().parents[2]
SENDER = ROOT / "ansible/roles/watchdog/files/vpn-watchdog-notify.py"
spec = importlib.util.spec_from_file_location("watchdog_notify", SENDER)
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


@pytest.fixture
def receiver():
    records = []
    entered = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            records.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": self.rfile.read(int(self.headers["Content-Length"])),
                }
            )
            entered.set()
            if self.path.endswith("stall"):
                release.wait(15)
            self.send_response(302 if self.path.endswith("/redirect") else 200)
            self.send_header("Location", "/unexpected")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], records, entered
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


def credentials(tmp_path, port, **changes):
    document = {
        "provider": "ntfy",
        "url": f"http://127.0.0.1:{port}",
        "topic": "synthetic-private-topic",
        "token": "synthetic-private-token",
    }
    document.update(changes)
    path = tmp_path / "notifications.json"
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    return path, document


def run_sender(tmp_path, timeout=1):
    return subprocess.run(
        [
            sys.executable,
            str(SENDER),
            "--title",
            "probe failed",
            "--tags",
            "warning,vpn",
            "--timeout",
            str(timeout),
        ],
        input="consecutive_fails=3",
        text=True,
        capture_output=True,
        env={**os.environ, "CREDENTIALS_DIRECTORY": str(tmp_path)},
        timeout=4,
    )


def test_ntfy_delivery_uses_private_credential_without_diagnostic_disclosure(
    tmp_path, receiver
):
    port, records, _ = receiver
    _, config = credentials(tmp_path, port)
    result = run_sender(tmp_path)
    assert result.returncode == 0, result.stderr
    assert records[0]["path"] == "/" + config["topic"]
    assert records[0]["headers"]["Authorization"] == "Bearer " + config["token"]
    assert records[0]["headers"]["Title"] == "probe failed"
    assert records[0]["body"] == b"consecutive_fails=3"
    assert not result.stdout and not result.stderr


def test_stalled_notification_has_absolute_deadline_and_no_secret_argv(
    tmp_path, receiver
):
    port, _, entered = receiver
    _, config = credentials(tmp_path, port, topic="synthetic-private-stall")
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, str(SENDER), "--title", "probe failed", "--timeout", "0.5"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "CREDENTIALS_DIRECTORY": str(tmp_path)},
        text=True,
    )
    try:
        process.stdin.write("failed")
        process.stdin.close()
        assert entered.wait(2)
        command = subprocess.run(
            ["ps", "-p", str(process.pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        environment = subprocess.run(
            ["ps", "eww", "-p", str(process.pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert config["token"] not in command
        assert config["topic"] not in command
        assert config["token"] not in environment
        assert config["topic"] not in environment
        process.wait(timeout=2)
        stderr = process.stderr.read()
        assert process.returncode == 1
        assert time.monotonic() - started < 2
        assert stderr == "watchdog notification failed\n"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_redirect_is_refused_without_forwarding_authority(tmp_path, receiver):
    port, records, _ = receiver
    credentials(tmp_path, port, topic="redirect")
    result = run_sender(tmp_path)
    assert result.returncode == 1
    assert len(records) == 1
    assert result.stderr == "watchdog notification failed\n"


@pytest.mark.parametrize(
    "unsafe", ["missing", "symlink", "hardlink", "world-readable", "malformed"]
)
def test_unsafe_authority_is_refused_without_request(tmp_path, receiver, unsafe):
    port, records, _ = receiver
    path, _ = credentials(tmp_path, port)
    if unsafe == "missing":
        path.unlink()
    elif unsafe == "symlink":
        target = tmp_path / "target"
        path.rename(target)
        path.symlink_to(target)
    elif unsafe == "hardlink":
        os.link(path, tmp_path / "other")
    elif unsafe == "world-readable":
        path.chmod(0o644)
    else:
        path.write_text("synthetic-malformed-private-material")
    result = run_sender(tmp_path)
    assert result.returncode == 1
    assert records == []
    assert result.stderr == "watchdog notification failed\n"


def test_pushover_payload_keeps_credentials_inside_request(
    tmp_path, receiver, monkeypatch
):
    port, records, _ = receiver
    monkeypatch.setattr(
        sender.http.client,
        "HTTPSConnection",
        lambda *_args, **kwargs: http.client.HTTPConnection(
            "127.0.0.1", port, **kwargs
        ),
    )
    config = {"provider": "pushover", "token": "private-token", "user": "private-user"}
    sender.deliver(config, "failed", "", "details", 1)
    fields = parse_qs(records[0]["body"].decode())
    assert fields == {
        "token": ["private-token"],
        "user": ["private-user"],
        "title": ["failed"],
        "message": ["details"],
        "priority": ["1"],
    }
    assert records[0]["path"] == "/1/messages.json"


def test_public_plaintext_destination_is_refused():
    with pytest.raises(sender.DeliveryError, match="invalid-destination"):
        sender.deliver(
            {
                "provider": "ntfy",
                "url": "http://notify.example.test",
                "topic": "private-topic",
            },
            "failed",
            "",
            "details",
            1,
        )


def test_stalled_notification_does_not_prevent_watchdog_state_publication(
    tmp_path, receiver
):
    from tests.unit.test_watchdog_protocol_probe import _run_watchdog

    port, _, _ = receiver
    authority = tmp_path / "credentials"
    authority.mkdir()
    credentials(authority, port, topic="synthetic-private-stall")
    result = _run_watchdog(
        tmp_path,
        canary_status="500",
        notification_sender=SENDER,
        credential_directory=authority,
    )
    assert result.returncode == 1
    assert "notification delivery failed" in result.stderr
    state = (tmp_path / "state").read_text()
    assert "consecutive_fails=1" in state
    assert "alerts_this_hour=1" in state
    assert "synthetic-private" not in result.stdout + result.stderr
