"""Focused contract tests for the independent Tailnet rollback guard."""

from __future__ import annotations
import importlib.util, json, os, subprocess, sys, threading
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/tailnet-network-executor.py"


def mod():
    spec = importlib.util.spec_from_file_location("tailnet_network_executor", SCRIPT)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(value)
    return value


def request():
    return {
        "server_uuid": "123e4567-e89b-42d3-a456-426614174000",
        "environment": "prod",
        "provider_target_sha256": "a" * 64,
        "forward_plan_sha256": "b" * 64,
        "guest_generation": "123e4567-e89b-42d3-a456-426614174000",
        "guest_nonce": "c" * 64,
        "guest_snapshot_digest": "d" * 64,
        "guest_deadline": 2_000,
    }


class Plan:
    def close(self):
        pass


class Adapter:
    def __init__(self):
        self.target = type("T", (), {"digest": "a" * 64})()
        self.calls = []

    def plan(self, direction):
        self.calls.append(("plan", direction))
        return Plan()

    def apply(self, direction, plan):
        self.calls.append(("apply", direction))


def executor(m, root):
    value = m.Executor.__new__(m.Executor)
    value.store = m.ReceiptStore(root)
    value.adapter = Adapter()
    value.target = value.adapter.target
    return value


def test_crash_after_provider_apply_reconciles_to_independent_false_apply(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    armed = value.guard(
        "begin-forward", {k: v for k, v in armed.items() if k != "state"}
    )
    applied = value.guard(
        "mark-applied",
        {
            **{k: v for k, v in armed.items() if k != "state"},
            "provider_applied_at": 1_001,
        },
    )
    assert applied["state"] == "provider-applied"
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    assert value.reconcile() == {"state": "executed"}
    assert value.adapter.calls == [("plan", "rollback"), ("apply", "rollback")]
    assert value.guard("execute", value.store.get()) == {"state": "executed"}
    next_request = {
        **request(),
        "forward_plan_sha256": "e" * 64,
        "guest_deadline": 3_000,
    }
    monkeypatch.setattr(m.time, "time", lambda: 2_100)
    assert value.guard("arm", next_request)["state"] == "armed"


def test_release_prevents_deadline_rollback_and_restart_reads_canonical_receipt(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    armed = value.guard(
        "begin-forward", {k: v for k, v in armed.items() if k != "state"}
    )
    applied = value.guard(
        "mark-applied",
        {
            **{k: v for k, v in armed.items() if k != "state"},
            "provider_applied_at": 1_001,
        },
    )
    committed = value.guard(
        "commit",
        {
            **{k: v for k, v in applied.items() if k != "state"},
            "promotion_observed_at": 1_002,
        },
    )
    assert value.guard("release", committed) == {"state": "released"}
    assert executor(m, tmp_path).reconcile() is None
    assert value.adapter.calls == []


def test_foreign_or_stale_receipt_fails_closed(tmp_path, monkeypatch):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    with pytest.raises(m.ExecutorError, match="receipt-foreign"):
        value.guard("inspect", {**armed, "guest_nonce": "e" * 64})
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    with pytest.raises(m.ExecutorError, match="transition-refused"):
        value.guard("execute", armed)


def test_corrupt_receipt_and_stale_temp_fail_closed_before_reconcile(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    value.guard("arm", request())
    (tmp_path / ".receipt.deadbeef.tmp").write_text("stale")
    restarted = m.ReceiptStore(tmp_path)
    assert not (tmp_path / ".receipt.deadbeef.tmp").exists()
    (tmp_path / "receipt.json").write_text('{"payload":{},"sha256":"bad"}\n')
    with pytest.raises(m.ExecutorError, match="receipt-refused"):
        value.reconcile()
    assert value.adapter.calls == []


def test_receipt_short_write_does_not_publish_partial_file(tmp_path, monkeypatch):
    m = mod()
    store = m.ReceiptStore(tmp_path)
    monkeypatch.setattr(m.os, "write", lambda *_: 0)
    with pytest.raises(m.ExecutorError, match="receipt-write-failed"):
        store.put({"state": "executed"})
    assert not store.path.exists()


def test_canonical_wrong_identity_never_reconciles_provider(tmp_path, monkeypatch):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    bad = {
        **request(),
        "server_uuid": "not-a-uuid",
        "expires_at": 2_000,
        "state": "armed",
    }
    envelope = {
        "payload": bad,
        "sha256": __import__("hashlib").sha256(m.canonical(bad)).hexdigest(),
    }
    value.store.path.write_bytes(m.canonical(envelope))
    value.store.path.chmod(0o600)
    with pytest.raises(m.ExecutorError, match="receipt-refused"):
        value.reconcile()
    assert value.adapter.calls == []


def test_partial_transition_is_refused_without_overwriting_armed_receipt(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    with pytest.raises(m.ExecutorError, match="receipt-refused"):
        value.guard("mark-applied", {"state": "armed"})
    assert value.store.get() == armed


def test_expired_armed_false_readback_terminalizes_without_provider_apply(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    value.target.value = {
        "server_uuid": request()["server_uuid"],
        "environment": "prod",
    }
    value.guard("arm", request())
    value._readback = lambda *_: {"firewall": False}
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    assert value.reconcile() == {"state": "executed"}
    assert value.adapter.calls == [] and value.store.get()["state"] == "executed"


def test_expiry_serializes_with_forward_mark_and_rolls_back_true(tmp_path, monkeypatch):
    """A stale timer observation cannot terminalize across a live forward lock."""
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    forward = value.guard(
        "begin-forward", {k: v for k, v in armed.items() if k != "state"}
    )
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    provider_lock = value.store._provider_locked()
    outcome = []

    def reconcile():
        outcome.append(value.reconcile())

    worker = threading.Thread(target=reconcile)
    worker.start()
    # The timer has observed the expired forward but cannot cross the provider
    # lock while the controller persists its successful publication marker.
    value.guard(
        "mark-applied",
        {
            **{k: v for k, v in forward.items() if k != "state"},
            "provider_applied_at": 1_999,
        },
    )
    os.close(provider_lock)
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert outcome == [{"state": "executed"}]
    assert value.adapter.calls == [("plan", "rollback"), ("apply", "rollback")]
    assert value.store.get()["state"] == "executed"


def test_partial_execute_and_release_requests_preserve_current_receipt(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    forward = value.guard(
        "begin-forward", {k: v for k, v in armed.items() if k != "state"}
    )
    applied = value.guard(
        "mark-applied",
        {
            **{k: v for k, v in forward.items() if k != "state"},
            "provider_applied_at": 1_001,
        },
    )
    with pytest.raises(m.ExecutorError, match="receipt-refused"):
        value.guard("execute", {"state": "provider-applied"})
    assert value.store.get() == applied
    debt = value.guard(
        "commit",
        {
            **{k: v for k, v in applied.items() if k != "state"},
            "promotion_observed_at": 1_002,
        },
    )
    with pytest.raises(m.ExecutorError, match="receipt-refused"):
        value.guard("release", {"state": "committed-cleanup-debt"})
    assert value.store.get() == debt


def test_deadline_terminalization_exits_daemon_and_removes_socket_pid(
    tmp_path, monkeypatch
):
    import shutil
    import tempfile

    m = mod()
    runtime = Path(tempfile.mkdtemp(prefix="tnterm-", dir="/private/tmp"))
    socket_path = runtime / "executor.sock"
    receipt_root = runtime / "state"

    class Store:
        pid = receipt_root / "daemon.json"

        def write_pid(self, value):
            receipt_root.mkdir(mode=0o700)
            self.pid.write_bytes(m.canonical(value))

    class FakeExecutor:
        def __init__(self, *_args):
            self.store = Store()
            self.target = type("Target", (), {"digest": "a" * 64})()

        def reconcile(self):
            return {"state": "executed"}

        def close(self):
            pass

    monkeypatch.setattr(m, "Executor", FakeExecutor)
    args = type(
        "Args",
        (),
        {
            "target": "target",
            "state": "state",
            "terraform": "terraform",
            "terraform_sha256": "a" * 64,
            "receipt_dir": str(receipt_root),
            "socket": str(socket_path),
        },
    )()
    try:
        m.serve(args)
        assert not socket_path.exists()
        assert not (receipt_root / "daemon.json").exists()
    finally:
        shutil.rmtree(runtime)


def test_controller_guest_rpc_is_fixed_strict_command_and_dry_run_disables_apply(
    monkeypatch, tmp_path
):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller", controller_path
    )
    c = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(c)
    command = []
    monkeypatch.setattr(
        c.p,
        "_bounded",
        lambda argv, *_a, **kw: command.append((argv, kw["input_data"]))
        or b'{"state":"prepared"}',
    )
    host = {
        "name": "node-a",
        "alias": "node-a",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "/private/key",
        "user": "deploy",
        "ssh_host_key_alias": "node-a",
    }
    (tmp_path / "known").write_text("node-a ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI\n")
    rpc = c.strict_guest(host, tmp_path / "known", b"fragment")
    rpc({}, "prepare", {}, False)
    assert (
        command[0][0][-1]
        == "sudo -n /usr/bin/python3 -I -B " + c.GUEST_HELPER + " prepare"
    )
    assert "-S -" not in command[0][0][-1]
    target = type("Target", (), {"value": {}, "digest": "a" * 64})()
    adapter = type("Adapter", (), {"target": target, "allow_apply": False})()
    assert adapter.allow_apply is False


def test_make_target_preserves_literal_config_until_controller_boundary():
    result = subprocess.run(
        [
            "make",
            "-n",
            "tailnet-network-promote",
            "TAILNET_NETWORK_CONFIG=$(shell false)",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"$TAILNET_NETWORK_CONFIG"' in result.stdout


def test_daemon_partial_client_is_bounded_and_remains_reachable(tmp_path, monkeypatch):
    """A controller crash mid-frame cannot monopolize the recovery daemon."""
    import shutil, socket, tempfile, time

    server = "123e4567-e89b-42d3-a456-426614174000"
    state = {
        "resources": [
            {
                "mode": "managed",
                "type": "upcloud_server",
                "name": "vpn",
                "instances": [{"attributes": {"id": server}}],
            }
        ],
        "outputs": {"server_ipv4": {"value": "198.51.100.1"}},
    }
    state_raw = json.dumps(state, separators=(",", ":")).encode()
    target = {
        "schema_version": 1,
        "provider": "upcloud",
        "environment": "prod",
        "server_uuid": server,
        "inventory_alias": "node-a",
        "public_service_address_sha256": __import__("hashlib")
        .sha256(b"198.51.100.1")
        .hexdigest(),
        "deployable_digest": "a" * 64,
        "state_sha256": __import__("hashlib").sha256(state_raw).hexdigest(),
    }
    target_path, state_path, binary = (
        tmp_path / "target",
        tmp_path / "state",
        tmp_path / "terraform",
    )
    target_path.write_bytes(
        (json.dumps(target, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    state_path.write_bytes(state_raw)
    binary.write_bytes(b"#!/bin/sh\nexit 0\n")
    for path in (target_path, state_path):
        path.chmod(0o600)
    binary.chmod(0o700)
    runtime = Path(tempfile.mkdtemp(prefix="tnexec-", dir="/private/tmp"))
    sock, root = runtime / "executor.sock", runtime / "state-root"
    env = {**os.environ, "UPCLOUD_TOKEN": "test-token"}
    command = [
        sys.executable,
        str(SCRIPT),
        "serve",
        "--target",
        str(target_path),
        "--state",
        str(state_path),
        "--terraform",
        str(binary),
        "--terraform-sha256",
        __import__("hashlib").sha256(binary.read_bytes()).hexdigest(),
        "--receipt-dir",
        str(root),
        "--socket",
    ]
    # AF_UNIX bind fails only after the daemon has persisted its PID identity.
    prebind = subprocess.run(
        [*command, str(runtime / ("x" * 120))], env=env, capture_output=True, text=True
    )
    assert prebind.returncode == 1 and (root / "daemon.json").exists()
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_recovery", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)
    controller._remove_verified_stale_executor(
        root,
        sock,
        __import__("hashlib").sha256(target_path.read_bytes()).hexdigest(),
        socket_required=False,
    )
    assert not (root / "daemon.json").exists()
    process = subprocess.Popen(
        [*command, str(sock)],
        env=env,
    )
    try:
        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.05)
        assert sock.exists(), process.poll()
        stuck = socket.socket(socket.AF_UNIX)
        stuck.connect(str(sock))
        stuck.sendall(b'{"action":"ping"')
        time.sleep(6)
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(2)
            client.connect(str(sock))
            client.sendall(b'{"action":"ping","value":{}}')
            client.shutdown(socket.SHUT_WR)
            assert (
                json.loads(client.recv(4096))["ok"]["provider_target_sha256"]
                == __import__("hashlib").sha256(target_path.read_bytes()).hexdigest()
            )
        assert process.poll() is None
        stuck.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
        shutil.rmtree(runtime)
