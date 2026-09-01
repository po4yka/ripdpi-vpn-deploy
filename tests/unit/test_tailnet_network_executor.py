"""Focused contract tests for the independent Tailnet rollback guard."""

from __future__ import annotations
import importlib.util, json, os, subprocess, sys, tempfile, threading
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/tailnet-network-executor.py"


def _short_temp_root(private_tmp: Path = Path("/private/tmp")) -> Path:
    """Keep AF_UNIX fixtures short while remaining portable to Linux runners."""
    return private_tmp if private_tmp.is_dir() else Path(tempfile.gettempdir())


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


def test_short_temp_root_falls_back_when_macos_private_tmp_is_absent(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    assert _short_temp_root(tmp_path / "absent") == tmp_path


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
    value.target.value = {
        "server_uuid": request()["server_uuid"],
        "environment": "prod",
    }
    value._readback = lambda *_args: {"firewall": True}
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
    m.ReceiptStore(tmp_path)
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


def test_expired_armed_receipt_cannot_begin_forward(tmp_path, monkeypatch):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    monkeypatch.setattr(m.time, "time", lambda: armed["expires_at"])
    with pytest.raises(m.ExecutorError, match="receipt-expired"):
        value.guard(
            "begin-forward",
            {key: item for key, item in armed.items() if key != "state"},
        )
    assert value.store.get() == armed


def test_expired_forward_started_false_readback_terminalizes_without_apply(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    value.target.value = {
        "server_uuid": request()["server_uuid"],
        "environment": "prod",
    }
    armed = value.guard("arm", request())
    value.guard(
        "begin-forward", {key: item for key, item in armed.items() if key != "state"}
    )
    value._readback = lambda *_: {"firewall": False}
    monkeypatch.setattr(m.time, "time", lambda: 2_001)
    assert value.reconcile() == {"state": "executed"}
    assert value.adapter.calls == []
    terminal = value.store.get()
    assert terminal["state"] == "executed" and "forward_lease" in terminal


def test_terminal_receipt_rejects_malformed_forward_lease(tmp_path):
    m = mod()
    value = executor(m, tmp_path)
    terminal = {
        **request(),
        "state": "executed",
        "executed_at": 1_001,
        "forward_lease": "not-a-lease",
    }
    with pytest.raises(m.ExecutorError, match="receipt-refused"):
        value._valid_current(terminal)


def test_expiry_serializes_with_forward_mark_and_rolls_back_true(tmp_path, monkeypatch):
    """A stale timer observation cannot terminalize across a live forward lock."""
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    armed = value.guard("arm", request())
    forward = value.guard(
        "begin-forward", {k: v for k, v in armed.items() if k != "state"}
    )
    value.target.value = {
        "server_uuid": request()["server_uuid"],
        "environment": "prod",
    }
    value._readback = lambda *_args: {"firewall": True}
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

    m = mod()
    runtime = Path(tempfile.mkdtemp(prefix="tnterm-", dir=_short_temp_root()))
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
            self.daemon_identity = {
                "provider_target_sha256": "a" * 64,
                "terraform_sha256": "b" * 64,
                "provider_capability_sha256": "c" * 64,
            }

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
    assert json.loads(command[0][1])["timeout"] == c.PREPARE_TIMEOUT
    assert len(command[0][1]) <= 64 * 1024
    target = type("Target", (), {"value": {}, "digest": "a" * 64})()
    adapter = type("Adapter", (), {"target": target, "allow_apply": False})()
    assert adapter.allow_apply is False


def test_controller_candidate_ceiling_matches_the_guest_json_frame(
    monkeypatch, tmp_path
):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_ceiling", controller_path
    )
    c = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(c)
    payloads = []
    monkeypatch.setattr(
        c.p.fleet_inspection,
        "ssh_command",
        lambda *_args: ["ssh", "host", "command"],
    )
    monkeypatch.setattr(
        c.p,
        "_bounded",
        lambda _argv, _env, **kwargs: payloads.append(kwargs["input_data"])
        or b'{"status":"prepared"}',
    )
    host = {"name": "node-a"}
    c.strict_guest(host, tmp_path / "known", b"x" * c.MAX_CANDIDATE)(
        host, "prepare", {}, False
    )
    assert len(payloads[0]) <= 64 * 1024
    with pytest.raises(c.p.PromotionError, match="guest-uncertain"):
        c.strict_guest(host, tmp_path / "known", b"x" * (c.MAX_CANDIDATE + 1))


def test_active_false_receipt_reconciles_provider_then_guest_before_terminal(
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
    value._readback = lambda *_args: {"firewall": False}

    current = value.guard("reconcile", {})
    assert current["state"] == "armed"
    assert value.guard("rollback-provider", current) == current
    assert value.adapter.calls == []
    assert value.guard("execute", current) == {"state": "executed"}


def test_provider_applied_reconcile_retries_guest_without_second_provider_apply(
    tmp_path, monkeypatch
):
    m = mod()
    value = executor(m, tmp_path)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    value.target.value = {
        "server_uuid": request()["server_uuid"],
        "environment": "prod",
    }
    armed = value.guard("arm", request())
    forward = value.guard(
        "begin-forward", {key: item for key, item in armed.items() if key != "state"}
    )
    current = value.guard(
        "mark-applied",
        {
            **{key: item for key, item in forward.items() if key != "state"},
            "provider_applied_at": 1_001,
        },
    )
    provider_firewall = {"enabled": True}
    original_apply = value.adapter.apply

    def apply(direction, plan):
        original_apply(direction, plan)
        provider_firewall["enabled"] = False

    value.adapter.apply = apply
    value._readback = lambda *_args: {"firewall": provider_firewall["enabled"]}

    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_actual_reconcile", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)
    identity = {
        "generation": current["guest_generation"],
        "nonce": current["guest_nonce"],
        "snapshot_digest": current["guest_snapshot_digest"],
        "deadline": current["guest_deadline"],
    }
    attempts = {"rollback": 0}

    def guest(_host, action, payload, _cleanup):
        if action == "status":
            return {**identity, "status": "applied"}
        assert action == "rollback" and payload == identity
        attempts["rollback"] += 1
        if attempts["rollback"] == 1:
            raise controller.p.PromotionError("rollback-uncertain")
        return {**identity, "status": "rolled_back"}

    with pytest.raises(controller.p.PromotionError, match="rollback-uncertain"):
        controller._reconcile_previous(value.guard, guest, {"name": "node-a"})
    assert value.store.get()["state"] == "provider-applied"
    assert value.adapter.calls == [("plan", "rollback"), ("apply", "rollback")]

    controller._reconcile_previous(value.guard, guest, {"name": "node-a"})
    assert value.adapter.calls == [("plan", "rollback"), ("apply", "rollback")]
    assert value.store.get()["state"] == "executed"


def test_controller_reconcile_rolls_back_guest_before_terminalizing_executor():
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_reconcile", controller_path
    )
    c = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(c)
    current = {**request(), "state": "provider-applied", "provider_applied_at": 1_001}
    calls = []

    def rollback_guard(action, value):
        calls.append(("provider", action))
        if action == "reconcile":
            return current
        if action == "rollback-provider":
            assert value == current
            return current
        if action == "execute":
            assert value == current
            return {"state": "executed"}
        raise AssertionError(action)

    identity = {
        "generation": current["guest_generation"],
        "nonce": current["guest_nonce"],
        "snapshot_digest": current["guest_snapshot_digest"],
        "deadline": current["guest_deadline"],
    }

    def guest(_host, action, value, _cleanup):
        calls.append(("guest", action))
        if action == "status":
            return {**identity, "status": "applied"}
        assert action == "rollback" and value == identity
        return {**identity, "status": "rolled_back"}

    c._reconcile_previous(rollback_guard, guest, {"name": "node-a"})
    assert calls == [
        ("provider", "reconcile"),
        ("guest", "status"),
        ("provider", "rollback-provider"),
        ("guest", "rollback"),
        ("provider", "execute"),
    ]


def test_spawn_timeout_reaps_owned_process_before_controller_returns(
    monkeypatch, tmp_path
):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_spawn_timeout", controller_path
    )
    c = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(c)

    class Process:
        terminated = False
        killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("executor", timeout)
            return 0

    process = Process()
    c._reap_spawned_process(process)
    assert process.terminated and process.killed


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(2)])
def test_spawn_wait_interrupt_reaps_credential_bearing_child(
    monkeypatch, tmp_path, failure
):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_spawn_interrupt", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)

    class Process:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, **_kwargs):
            return 0

    process = Process()
    monkeypatch.setattr(
        controller,
        "_wait_for_spawned_executor",
        lambda *_args: (_ for _ in ()).throw(failure),
    )
    with pytest.raises(type(failure)):
        controller._wait_or_reap_spawned_executor(
            process, tmp_path / "executor.sock", {"token_sha256": "a" * 64}
        )
    assert process.terminated


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


def test_controller_freezes_one_inventory_host_for_guest_provider_and_proof(
    monkeypatch, tmp_path
):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_frozen_host", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)
    host_a = {"name": "node-a", "address": "192.0.2.10", "port": 22}
    host_b = {"name": "node-b", "address": "192.0.2.11", "port": 22}
    selections = []

    def select_hosts(*_args):
        selections.append(True)
        return [host_a if len(selections) == 1 else host_b]

    monkeypatch.setattr(controller.p.fleet_inspection, "select_hosts", select_hosts)
    monkeypatch.setattr(controller, "private_directory", lambda _path: None)
    guest_hosts = []

    def strict_guest(host, *_args):
        guest_hosts.append(host)
        return lambda *_call: {"status": "unchanged"}

    monkeypatch.setattr(controller, "strict_guest", strict_guest)

    class Owned:
        def __init__(self, *fds):
            self.fds = list(fds)

        def close(self):
            while self.fds:
                os.close(self.fds.pop())

    class Target(Owned):
        def __init__(self, *fds):
            super().__init__(*fds)
            self.digest = "a" * 64
            self.value = {
                "inventory_alias": "node-a",
                "public_service_address_sha256": "b" * 64,
                "deployable_digest": "c" * 64,
            }

    class Trusted(Owned):
        def __init__(self, fd, _digest):
            super().__init__(fd)
            self.digest = "d" * 64

    class Adapter:
        def __init__(self, target, *, trusted_terraform, **_kwargs):
            self.target = target
            self.trusted = trusted_terraform
            self.environment_map = {}

        def close(self):
            self.target.close()
            self.trusted.close()

    monkeypatch.setattr(controller.p, "ProviderTarget", Target)
    monkeypatch.setattr(controller.p, "TrustedTerraform", Trusted)
    monkeypatch.setattr(controller.p, "TerraformAdapter", Adapter)
    observed = {}

    def execute(request, adapter, *, guest, selected_host=None, **_kwargs):
        # A regression that omits selected_host would force a second inventory
        # read here and bind the provider/proof to node B.
        chosen = selected_host or select_hosts()[0]
        observed.update(
            host=chosen,
            alias=request["target_identity"]["inventory_alias"],
            guest=guest("preview", {}),
        )
        adapter.close()
        return {"status": "dry-run"}

    monkeypatch.setattr(controller.p, "execute", execute)
    files = {}
    for name, content, mode in (
        ("target", b"target", 0o600),
        ("state", b"state", 0o600),
        ("terraform", b"#!/bin/sh\n", 0o700),
        ("candidate", b"define set vpn_tailnet_ssh_v4 = { 100.64.0.1 }\n", 0o600),
    ):
        files[name] = tmp_path / name
        files[name].write_bytes(content)
        files[name].chmod(mode)

    result = controller.run(
        {
            "inventory_path": str(tmp_path / "inventory"),
            "inventory_name": "node-a",
            "provider_target_path": str(files["target"]),
            "provider_state_path": str(files["state"]),
            "terraform_path": str(files["terraform"]),
            "terraform_sha256": "d" * 64,
            "candidate_fragment_path": str(files["candidate"]),
            "executor_dir": str(tmp_path / "executor"),
            "known_hosts_path": str(tmp_path / "known"),
            "contexts": [],
            "mode": "dry-run",
            "promotion_config_path": str(tmp_path / "config"),
        }
    )
    assert result == {"status": "dry-run"}
    assert len(selections) == 1
    assert guest_hosts == [host_a]
    assert observed == {
        "host": host_a,
        "alias": "node-a",
        "guest": {"status": "unchanged"},
    }


@pytest.mark.parametrize(
    ("stage", "interruption"),
    [
        ("adapter", KeyboardInterrupt()),
        ("adapter", SystemExit(2)),
        ("reconcile", KeyboardInterrupt()),
        ("reconcile", SystemExit(2)),
    ],
)
def test_controller_reaps_unarmed_executor_when_reconcile_is_interrupted(
    monkeypatch, tmp_path, stage, interruption
):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_reconcile_interrupt", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)
    host = {"name": "node-a", "address": "192.0.2.10", "port": 22}
    monkeypatch.setattr(
        controller.p.fleet_inspection, "select_hosts", lambda *_args: [host]
    )
    monkeypatch.setattr(controller, "private_directory", lambda _path: None)
    monkeypatch.setenv("UPCLOUD_TOKEN", "fixture-token")

    class Owned:
        def __init__(self, *fds):
            self.fds = list(fds)

        def close(self):
            while self.fds:
                os.close(self.fds.pop())

    class Target(Owned):
        def __init__(self, *fds):
            super().__init__(*fds)
            self.digest = "a" * 64
            self.value = {
                "inventory_alias": "node-a",
                "public_service_address_sha256": "b" * 64,
                "deployable_digest": "c" * 64,
            }

    class Trusted(Owned):
        def __init__(self, fd, _digest):
            super().__init__(fd)
            self.digest = "d" * 64

    class Adapter:
        def __init__(self, target, *, trusted_terraform, **_kwargs):
            if stage == "adapter":
                raise interruption
            self.target = target
            self.trusted = trusted_terraform
            self.environment_map = {}

        def close(self):
            self.target.close()
            self.trusted.close()

    class Process:
        pass

    process = Process()
    monkeypatch.setattr(controller.p, "ProviderTarget", Target)
    monkeypatch.setattr(controller.p, "TrustedTerraform", Trusted)
    monkeypatch.setattr(controller.p, "TerraformAdapter", Adapter)
    monkeypatch.setattr(controller.subprocess, "Popen", lambda *_a, **_k: process)
    monkeypatch.setattr(controller, "_wait_or_reap_spawned_executor", lambda *_: None)
    monkeypatch.setattr(controller, "strict_guest", lambda *_: lambda *_call: {})
    monkeypatch.setattr(
        controller,
        "_reconcile_previous",
        lambda *_: (
            (_ for _ in ()).throw(interruption) if stage == "reconcile" else None
        ),
    )
    reaped = []
    monkeypatch.setattr(
        controller,
        "_terminate_unarmed_executor",
        lambda child, *_args: reaped.append(child),
    )
    files = {}
    for name, content, mode in (
        ("target", b"target", 0o600),
        ("state", b"state", 0o600),
        ("terraform", b"#!/bin/sh\n", 0o700),
        ("candidate", b"define set vpn_tailnet_ssh_v4 = { 100.64.0.1 }\n", 0o600),
    ):
        files[name] = tmp_path / name
        files[name].write_bytes(content)
        files[name].chmod(mode)

    with pytest.raises(type(interruption)):
        controller.run(
            {
                "inventory_path": str(tmp_path / "inventory"),
                "inventory_name": "node-a",
                "provider_target_path": str(files["target"]),
                "provider_state_path": str(files["state"]),
                "terraform_path": str(files["terraform"]),
                "terraform_sha256": "d" * 64,
                "candidate_fragment_path": str(files["candidate"]),
                "executor_dir": str(tmp_path / "executor"),
                "known_hosts_path": str(tmp_path / "known"),
                "contexts": [],
                "mode": "apply",
                "promotion_config_path": str(tmp_path / "config"),
            }
        )
    assert reaped == [process]


def test_daemon_partial_client_is_bounded_and_remains_reachable(tmp_path, monkeypatch):
    """A controller crash mid-frame cannot monopolize the recovery daemon."""
    import shutil, socket, time

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
    runtime = Path(tempfile.mkdtemp(prefix="tnexec-", dir=_short_temp_root()))
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
    identity = controller.executor_identity(
        __import__("hashlib").sha256(target_path.read_bytes()).hexdigest(),
        __import__("hashlib").sha256(binary.read_bytes()).hexdigest(),
        "test-token",
    )
    controller._remove_verified_stale_executor(
        root,
        sock,
        identity,
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
            assert json.loads(client.recv(4096))["ok"] == {
                "identity": identity,
                "receipt_state": None,
            }
        assert process.poll() is None
        stuck.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
        shutil.rmtree(runtime)


def test_controller_two_invocations_reject_unarmed_or_changed_executor(
    monkeypatch, tmp_path
):
    """An unarmed daemon cannot outlive the exact Terraform/capability authority."""
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_identity", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)
    first = controller.executor_identity("a" * 64, "b" * 64, "first-token")
    changed_terraform = controller.executor_identity("a" * 64, "c" * 64, "first-token")
    changed_capability = controller.executor_identity(
        "a" * 64, "b" * 64, "second-token"
    )
    assert (
        first["provider_capability_sha256"]
        != changed_capability["provider_capability_sha256"]
    )

    def ping(_socket):
        return lambda *_args: {"identity": first, "receipt_state": None}

    monkeypatch.setattr(controller, "guard", ping)
    assert not controller._live_executor(Path("/private/executor.sock"), first)

    # A first controller can die after spawning but before arming.  The next
    # invocation must reject that live orphan rather than borrowing its
    # provider capability.
    daemon = tmp_path / "daemon.json"
    daemon.write_text(
        json.dumps({"schema_version": 2, "pid": os.getpid(), **first}) + "\n"
    )
    daemon.chmod(0o600)
    with pytest.raises(controller.ControllerError, match="executor-unreachable"):
        controller._remove_verified_stale_executor(
            tmp_path, tmp_path / "executor.sock", first, socket_required=False
        )

    def armed_ping(_socket):
        return lambda *_args: {"identity": first, "receipt_state": "armed"}

    monkeypatch.setattr(controller, "guard", armed_ping)
    assert controller._live_executor(Path("/private/executor.sock"), first)
    assert not controller._live_executor(
        Path("/private/executor.sock"), changed_terraform
    )
    assert not controller._live_executor(
        Path("/private/executor.sock"), changed_capability
    )


def test_spawn_wait_revalidates_identity_before_second_controller_can_arm(
    monkeypatch, tmp_path
):
    """A socket created by controller A cannot be accepted by controller B."""
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_controller_spawn_identity", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)
    first = controller.executor_identity("a" * 64, "b" * 64, "first-token")
    second = controller.executor_identity("a" * 64, "b" * 64, "second-token")
    socket_path = tmp_path / "executor.sock"
    socket_path.write_text("not-a-socket")

    class Process:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, **_kwargs):
            return 0

    process = Process()

    def first_daemon(_socket):
        return lambda *_args: {"identity": first, "receipt_state": None}

    monkeypatch.setattr(controller, "guard", first_daemon)
    with pytest.raises(controller.ControllerError, match="executor-identity-refused"):
        controller._wait_for_spawned_executor(process, socket_path, second)
    assert process.terminated


def test_controller_reaps_a_spawned_unarmed_executor_after_prepare_failure(
    monkeypatch, tmp_path
):
    controller_path = ROOT / "scripts/tailnet-network-controller.py"
    spec = importlib.util.spec_from_file_location(
        "tailnet_controller_reap", controller_path
    )
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(controller)
    identity = controller.executor_identity("a" * 64, "b" * 64, "token")

    class Process:
        alive = True
        terminated = False

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.terminated = True
            self.alive = False

        def wait(self, **_kwargs):
            return 0

    process = Process()
    monkeypatch.setattr(
        controller,
        "_live_executor",
        lambda *_args, **kwargs: kwargs.get("allow_unarmed", False),
    )
    controller._terminate_unarmed_executor(
        process, tmp_path / "executor.sock", identity
    )
    assert process.terminated
