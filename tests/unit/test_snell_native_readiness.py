"""Portable ownership and diagnostic tests, separate from native protocol proof."""
import os
import socket
import sys
import time
from contextlib import ExitStack

import pytest
import test_snell_native as native


def assert_reserved(port):
    with socket.socket() as contender, pytest.raises(OSError):
        contender.bind(("127.0.0.1", port))


def assert_released(ports):
    with ExitStack() as stack:
        for port in ports:
            stack.enter_context(socket.socket()).bind(("127.0.0.1", port))


def child_binary(tmp_path):
    binary = tmp_path / "owned-child"
    binary.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, socket, stat, sys, time
path = pathlib.Path(sys.argv[-1])
value = json.loads(path.read_text())
if sys.argv[1] == "check":
    for port in value["ports"]:
        with socket.socket() as contender:
            try:
                contender.bind(("127.0.0.1", port))
            except OSError:
                continue
            raise AssertionError("reservation released before parser check")
    if value["state"] == "parser-failure":
        print("private-parser-credential-canary", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
assert stat.S_IMODE(os.fstat(1).st_mode) == 0o600
path.with_suffix(".pid").write_text(str(os.getpid()))
if value["state"] in {"bind-conflict", "unknown"}:
    print("private-credential-canary " + ("bind: address already in use" if value["state"] == "bind-conflict" else "other private failure"), flush=True)
    sys.exit(1)
listeners = []
for port in value["ports"]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", port))
    listener.listen()
    listeners.append(listener)
if value["state"] != "timeout":
    print("sing-box started", flush=True)
time.sleep(60)
''')
    binary.chmod(0o700)
    return binary


def test_all_listener_reservations_are_distinct_and_reclaimed_on_exception():
    with pytest.raises(RuntimeError, match="owned interruption"), native.reserved_ports(5) as held:
        ports = [connection.getsockname()[1] for connection in held]
        assert len(set(ports)) == 5
        for port in ports:
            assert_reserved(port)
        raise RuntimeError("owned interruption")
    assert all(connection.fileno() == -1 for connection in held)
    assert_released(ports)


def test_partial_allocation_failure_reclaims_every_created_socket(monkeypatch):
    created = []
    class FailThirdBind(socket.socket):
        def bind(self, address):
            created.append(self)
            if len(created) == 3:
                raise OSError("owned allocation failure")
            return super().bind(address)
    monkeypatch.setattr(native.socket, "socket", FailThirdBind)
    with pytest.raises(OSError, match="owned allocation failure"), native.reserved_ports(5):
        pytest.fail("partial allocation must never yield")
    assert len(created) == 3 and all(connection.fileno() == -1 for connection in created)


def test_release_occurs_after_check_and_only_for_the_launched_process(tmp_path):
    binary = child_binary(tmp_path)
    with native.reserved_ports(5) as held:
        ports = [connection.getsockname()[1] for connection in held]
        path = tmp_path / "server.json"
        with native.engine(binary, path, {"ports": ports[:3], "state": "ready"}, held[:3]) as process:
            assert process.poll() is None
            assert all(connection.fileno() == -1 for connection in held[:3])
            assert all(connection.fileno() != -1 for connection in held[3:])
            for port in ports:
                assert_reserved(port)
        assert process.poll() is not None
    assert_released(ports)


@pytest.mark.parametrize("state", ["parser-failure", "bind-conflict", "unknown", "timeout"])
def test_startup_failures_are_bounded_private_and_reclaim_owned_resources(tmp_path, state):
    binary = child_binary(tmp_path)
    path = tmp_path / "server.json"
    expected = {"parser-failure": "real Snell parser refused role-generated configuration",
                "bind-conflict": "Snell engine startup failed: bind-conflict; exit=1",
                "unknown": "Snell engine startup failed: exited; exit=1",
                "timeout": "Snell engine startup failed: timeout"}[state]
    started = time.monotonic()
    with pytest.raises(AssertionError) as failure, native.reserved_ports(2) as held:
        ports = [connection.getsockname()[1] for connection in held]
        with native.engine(binary, path, {"ports": ports, "state": state}, held):
            pytest.fail("failed startup must never yield")
    assert str(failure.value).split("\n", 1)[0] == expected
    assert "private-" not in str(failure.value)
    assert time.monotonic() - started < 9
    assert all(connection.fileno() == -1 for connection in held)
    assert_released(ports)
    if state == "parser-failure":
        assert not path.with_suffix(".pid").exists()
    else:
        assert path.with_suffix(".log").stat().st_mode & 0o777 == 0o600
        with pytest.raises(ProcessLookupError):
            os.kill(int(path.with_suffix(".pid").read_text()), 0)


def test_startup_log_read_has_a_fixed_size_bound(tmp_path):
    path = tmp_path / "private.log"
    path.write_bytes(b"x" * 65536 + b"private-canary sing-box started")
    assert native.startup_log(path) == b"x" * 65536
