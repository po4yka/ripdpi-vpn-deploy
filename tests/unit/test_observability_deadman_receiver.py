"""Actual local TLS admission and durable receiver epoch regressions.

Synthetic loopback fixtures prove source behavior, never live topology acceptance.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
from urllib import request

import pytest

from tests.unit.test_observability_deadman import (
    NOW,
    SOURCE,
    TOKEN,
    _pulse_tls,
    config,
    deadman,
    instant,
    state,
)


def signed_pulse(
    *,
    generation: str = "a" * 40,
    sequence: int = 1,
    now: int = NOW,
    expiry: int | None = None,
) -> bytes:
    value = {
        "schema": 1,
        "generation": generation,
        "sequence": sequence,
        "issued_at": instant(now - 1),
        "expires_at": instant(now + 20 if expiry is None else expiry),
        "health": {
            "prometheus": True,
            "alertmanager": True,
            "canary": True,
            "primary_telegram": True,
        },
    }
    value["signature"] = hmac.new(
        TOKEN, deadman._canonical(value), hashlib.sha256
    ).hexdigest()
    return json.dumps(value, separators=(",", ":")).encode()


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def local_receiver(tmp_path: Path):  # type: ignore[no-untyped-def]
    identity = _pulse_tls()
    for name, value in {
        "pulse-server-cert": identity["server_cert_pem"],
        "pulse-server-key": identity["server_key_pem"],
        "pulse-ca": identity["ca_pem"],
        "pulse-token": TOKEN.decode(),
    }.items():
        credential = tmp_path / name
        credential.write_text(value)
        credential.chmod(0o600)
    configuration = tmp_path / "config.json"
    configuration.write_text(json.dumps(config()))
    persisted = tmp_path / "state.json"
    port, status_port = free_port(), free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            str(SOURCE),
            "serve",
            "--config",
            str(configuration),
            "--state",
            str(persisted),
            "--listen",
            f"127.0.0.1:{port}",
            "--status-listen",
            f"127.0.0.1:{status_port}",
        ],
        env={**os.environ, "CREDENTIALS_DIRECTORY": str(tmp_path)},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    context = ssl.create_default_context(cafile=str(tmp_path / "pulse-ca"))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ready = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with request.urlopen(
                    f"http://127.0.0.1:{status_port}/v1/status", timeout=0.2
                ) as response:
                    ready = response.status == 200
                    break
            except OSError:
                time.sleep(0.02)
        assert ready, "owned local receiver did not become ready"
        yield port, context, persisted, process
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        assert process.poll() is not None
        assert stdout == b"" and stderr == b""


def send_pulse(port: int, context: ssl.SSLContext, *, sequence: int = 1) -> int:
    raw = signed_pulse(now=int(time.time()), sequence=sequence)
    with request.urlopen(
        request.Request(f"https://localhost:{port}/v1/pulse", data=raw, method="POST"),
        context=context,
        timeout=2,
    ) as response:
        return response.status


def test_incomplete_tls_client_does_not_block_authenticated_pulse(
    tmp_path: Path,
) -> None:
    with local_receiver(tmp_path) as (port, context, persisted, _process):
        with socket.create_connection(("127.0.0.1", port), timeout=2) as incomplete:
            incomplete.sendall(b"\x16\x03")
            started = time.monotonic()
            result = send_pulse(port, context)
            assert result == 204
            assert time.monotonic() - started < 2
            assert deadman._state(persisted)["last_sequence"] == 1


def test_worker_capacity_is_bounded_before_tls_and_reclaimed_after_deadline(
    tmp_path: Path,
) -> None:
    with local_receiver(tmp_path) as (port, context, persisted, process):
        peers = []
        try:
            for _ in range(4):
                peer = socket.create_connection(("127.0.0.1", port), timeout=2)
                peer.sendall(b"\x16\x03")
                peers.append(peer)
            started = time.monotonic()
            with socket.create_connection(("127.0.0.1", port), timeout=2) as overflow:
                with pytest.raises((OSError, ssl.SSLError)):
                    context.wrap_socket(overflow, server_hostname="localhost")
            assert time.monotonic() - started < 2
            assert not persisted.exists()
            for peer in peers:
                peer.settimeout(6)
                assert peer.recv(1) == b""
            assert process.poll() is None
            result = send_pulse(port, context)
            assert result == 204
            assert deadman._state(persisted)["last_sequence"] == 1
        finally:
            for peer in peers:
                peer.close()


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_slow_drip_http_input_has_one_absolute_deadline(
    tmp_path: Path, phase: str
) -> None:
    with local_receiver(tmp_path) as (port, context, persisted, _process):
        with socket.create_connection(("127.0.0.1", port), timeout=2) as raw:
            with context.wrap_socket(raw, server_hostname="localhost") as peer:
                prefix = b"POST /v1/pulse HTTP/1.1\r\nHost: localhost\r\n"
                if phase == "body":
                    prefix += b"Content-Length: 4096\r\n\r\n"
                else:
                    prefix += b"X-Drip: "
                peer.sendall(prefix)
                started = time.monotonic()
                closed = False
                while time.monotonic() - started < 7:
                    try:
                        peer.sendall(b"x")
                    except OSError:
                        closed = True
                        break
                    time.sleep(0.1)
                assert closed
                assert time.monotonic() - started < 6.5
        assert not persisted.exists()
        result = send_pulse(port, context)
        assert result == 204


def test_aggregate_headers_refused_before_body_and_worker_reclaimed(
    tmp_path: Path,
) -> None:
    with local_receiver(tmp_path) as (port, context, persisted, _process):
        with socket.create_connection(("127.0.0.1", port), timeout=2) as raw:
            with context.wrap_socket(raw, server_hostname="localhost") as peer:
                peer.sendall(
                    b"POST /v1/pulse HTTP/1.1\r\nX-Large: " + b"x" * 13000 + b"\r\n"
                )
                assert peer.recv(1) == b""
        assert not persisted.exists()
        result = send_pulse(port, context)
        assert result == 204


def test_authorized_epoch_transition_resets_sequence_but_preserves_expiry_and_delivery(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    current = state()
    current.update(
        last_sequence=99,
        last_expiry=NOW + 10,
        incident=True,
        last_delivery="firing",
        pending_event="recovery",
        pending_nonce=2,
        pending_at=NOW,
    )
    deadman._save_state(path, current)
    candidate = config()
    candidate["source_generation"] = "b" * 40
    accepted = deadman.accept_and_save(
        path, signed_pulse(generation="b" * 40), TOKEN, candidate, NOW
    )
    assert accepted["source_generation"] == "b" * 40
    assert accepted["last_sequence"] == 1
    assert accepted["last_expiry"] == NOW + 20
    for name in (
        "incident",
        "last_delivery",
        "pending_event",
        "pending_nonce",
        "pending_at",
    ):
        assert accepted[name] == current[name]
    assert deadman._state(path) == accepted
    original = path.read_bytes()
    for raw in (
        signed_pulse(),
        signed_pulse(generation="c" * 40),
        signed_pulse(generation="b" * 40, expiry=NOW + 21),
        signed_pulse(generation="b" * 40, sequence=2, expiry=NOW + 20),
    ):
        with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
            deadman.accept_and_save(path, raw, TOKEN, candidate, NOW)
        assert path.read_bytes() == original


def test_generation_rollback_cannot_revive_previously_accepted_signed_pulse(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    old = signed_pulse(sequence=99, expiry=NOW + 10)
    deadman.accept_and_save(path, old, TOKEN, config(), NOW)
    candidate = config()
    candidate["source_generation"] = "b" * 40
    deadman.accept_and_save(
        path, signed_pulse(generation="b" * 40, expiry=NOW + 20), TOKEN, candidate, NOW
    )
    original = path.read_bytes()
    with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
        deadman.accept_and_save(path, old, TOKEN, config(), NOW)
    assert path.read_bytes() == original
    accepted = deadman.accept_and_save(
        path, signed_pulse(expiry=NOW + 21), TOKEN, config(), NOW
    )
    assert accepted["source_generation"] == "a" * 40
    assert accepted["last_sequence"] == 1


def test_bad_signature_or_unhealthy_epoch_cannot_mutate_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    current = state()
    current.update(last_sequence=99, last_expiry=NOW + 10, incident=True)
    deadman._save_state(path, current)
    original = path.read_bytes()
    candidate = config()
    candidate["source_generation"] = "b" * 40
    value = json.loads(signed_pulse(generation="b" * 40))
    value["signature"] = "0" * 64
    with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
        deadman.accept_and_save(path, json.dumps(value).encode(), TOKEN, candidate, NOW)
    assert path.read_bytes() == original
    value["health"]["canary"] = False
    value["signature"] = hmac.new(
        TOKEN, deadman._canonical(value), hashlib.sha256
    ).hexdigest()
    with pytest.raises(deadman.DeadmanError, match="unhealthy pulse"):
        deadman.accept_and_save(path, json.dumps(value).encode(), TOKEN, candidate, NOW)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "extra",
    [
        b"Content-Length: {length}\r\nContent-Length: {length}\r\n",
        b"Transfer-Encoding: chunked\r\nContent-Length: {length}\r\n",
        b"Content-Length: +{length}\r\n",
    ],
)
def test_ambiguous_http_framing_is_rejected_without_state_write(
    tmp_path: Path, extra: bytes
) -> None:
    with local_receiver(tmp_path) as (port, context, persisted, _process):
        body = signed_pulse(now=int(time.time()))
        headers = extra.replace(b"{length}", str(len(body)).encode())
        with socket.create_connection(("127.0.0.1", port), timeout=2) as raw:
            with context.wrap_socket(raw, server_hostname="localhost") as peer:
                peer.sendall(
                    b"POST /v1/pulse HTTP/1.1\r\nHost: localhost\r\n"
                    + headers
                    + b"\r\n"
                    + body
                )
                assert peer.recv(4096).startswith(b"HTTP/1.0 400")
        assert not persisted.exists()


def test_concurrent_epoch_transition_has_one_durable_winner(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    current = state()
    current.update(last_sequence=99, last_expiry=NOW + 10, incident=True)
    deadman._save_state(path, current)
    candidate = config()
    candidate["source_generation"] = "b" * 40
    raw = signed_pulse(generation="b" * 40)
    program = """
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location('receiver', sys.argv[1])
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
print('ready', flush=True)
sys.stdin.readline()
try:
    receiver.accept_and_save(pathlib.Path(sys.argv[2]), bytes.fromhex(sys.argv[3]),
        bytes.fromhex(sys.argv[4]), json.loads(sys.argv[5]), int(sys.argv[6]))
except receiver.DeadmanError:
    print('rejected', flush=True)
else:
    print('accepted', flush=True)
"""
    processes = []
    try:
        for _ in range(2):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        program,
                        str(SOURCE),
                        str(path),
                        raw.hex(),
                        TOKEN.hex(),
                        json.dumps(candidate),
                        str(NOW),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        for process in processes:
            assert process.stdout.readline().strip() == "ready"
        for process in processes:
            process.stdin.write("start\n")
            process.stdin.flush()
        outcomes = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 0 and stderr == ""
            outcomes.append(stdout.strip())
        assert sorted(outcomes) == ["accepted", "rejected"]
        persisted = deadman._state(path)
        assert persisted["source_generation"] == "b" * 40
        assert persisted["last_sequence"] == 1
        assert persisted["incident"] is True
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


@pytest.mark.parametrize("field", ["schema", "sequence"])
def test_signed_boolean_integer_alias_is_rejected(field: str) -> None:
    value = json.loads(signed_pulse())
    value[field] = True
    value["signature"] = hmac.new(
        TOKEN, deadman._canonical(value), hashlib.sha256
    ).hexdigest()
    with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
        deadman.accept_pulse(json.dumps(value).encode(), TOKEN, state(), config(), NOW)
