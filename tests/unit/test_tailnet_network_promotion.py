"""Unit coverage for the import-only provider/guest promotion core."""

from __future__ import annotations
import fcntl, hashlib, importlib.util, json, os
from pathlib import Path
import platform
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/tailnet-network-promotion.py"
SERVER = "123e4567-e89b-42d3-a456-426614174000"


def mod():
    spec = importlib.util.spec_from_file_location("tailnet_network_promotion", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def plan(before, after):
    old = {"id": SERVER, "firewall": before, "hostname": "vpn"}
    new = dict(old, firewall=after)
    noop = {
        "actions": ["no-op"],
        "before": {"id": "same"},
        "after": {"id": "same"},
        "after_unknown": {},
    }
    return json.dumps(
        {
            "format_version": "1.2",
            "resource_changes": [
                {
                    "address": "upcloud_server.vpn",
                    "type": "upcloud_server",
                    "name": "vpn",
                    "change": {
                        "actions": ["update"],
                        "before": old,
                        "after": new,
                        "after_unknown": {},
                    },
                },
                {
                    "address": "upcloud_firewall_rules.vpn",
                    "type": "upcloud_firewall_rules",
                    "name": "vpn",
                    "change": noop,
                },
                {
                    "address": "terraform_data.ssh_port",
                    "type": "terraform_data",
                    "name": "ssh_port",
                    "change": noop,
                },
            ],
        }
    ).encode()


def _target(
    m,
    tmp_path,
    *,
    alias="node-a",
    address="198.51.100.1",
    environment="staging",
    server_uuid=SERVER,
    state=None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if state is None:
        state = (
            json.dumps(
                {
                    "version": 4,
                    "outputs": {
                        "server_ipv4": {
                            "value": address,
                            "type": "string",
                            "sensitive": False,
                        }
                    },
                    "resources": [
                        {
                            "mode": "managed",
                            "type": "upcloud_server",
                            "name": "vpn",
                            "instances": [
                                {"attributes": {"id": server_uuid, "firewall": False}}
                            ],
                        }
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
    value = {
        "schema_version": 1,
        "provider": "upcloud",
        "environment": environment,
        "server_uuid": server_uuid,
        "inventory_alias": alias,
        "public_service_address_sha256": hashlib.sha256(address.encode()).hexdigest(),
        "deployable_digest": "b" * 64,
        "state_sha256": hashlib.sha256(state).hexdigest(),
    }
    path = tmp_path / ("provider-target-" + alias + ".json")
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    path.chmod(0o600)
    state_path = tmp_path / ("terraform-state-" + alias + ".json")
    state_path.write_bytes(state)
    state_path.chmod(0o600)
    return m.ProviderTarget(
        os.open(path, os.O_RDONLY), os.open(state_path, os.O_RDONLY)
    )


def test_review_accepts_only_exact_upcloud_firewall_flip_and_noop_siblings():
    m = mod()
    m.review_plan(plan(False, True), SERVER, False, True)
    bad = json.loads(plan(False, True))
    bad["resource_changes"][1]["change"]["actions"] = ["update"]
    with pytest.raises(m.PromotionError, match="provider-plan-invalid"):
        m.review_plan(json.dumps(bad).encode(), SERVER, False, True)


def test_saved_plan_is_private_unlinked_and_uses_native_fd_path(tmp_path):
    m = mod()
    path = tmp_path / "plan"
    path.write_bytes(b"x")
    path.chmod(0o600)
    fd = os.open(path, os.O_RDONLY)
    os.unlink(path)
    saved = m.SavedPlan(fd)
    assert saved.path().endswith(str(fd))
    assert os.fstat(fd).st_nlink == 0
    saved.close()
    saved.close()
    with pytest.raises(m.PromotionError, match="provider-plan-closed"):
        saved.path()


def test_adapter_has_no_apply_authority_without_both_injected_guards(tmp_path):
    m = mod()
    adapter = m.TerraformAdapter(_target(m, tmp_path))
    with pytest.raises(m.PromotionError, match="provider-apply-not-authorized"):
        adapter.apply("forward", object())


def test_adapter_refuses_plan_without_a_reviewed_executable_capability(tmp_path):
    m = mod()
    adapter = m.TerraformAdapter(_target(m, tmp_path))
    with pytest.raises(m.PromotionError, match="terraform-executable-not-trusted"):
        adapter.plan("forward")


def test_promotion_proof_is_a_single_explicit_dependency():
    source = SCRIPT.read_text()
    assert source.count("proof_result = promotion_proof(") == 1
    assert source.count("sshd-promotion-proof.py") == 1


class Adapter:
    environment = "staging"

    def __init__(self):
        self.calls = []
        self._plans = set()
        self.capability = (("state", "armed"),)

    class Plan:
        def close(self):
            pass

    def plan(self, direction):
        value = self.Plan()
        self.calls.append(("plan", direction))
        self._plans.add(value)
        return value

    def apply(self, direction, value):
        self.calls.append(("apply", direction))
        self._plans.discard(value)

    def arm_rollback(self, _forward, _guest):
        self.calls.append(("arm",))
        return self.capability

    def mark_applied(self, _capability, when):
        self.calls.append(("mark-applied",))
        self.capability = (("provider_applied_at", when), ("state", "provider-applied"))
        return self.capability

    def begin_forward(self, _capability):
        self.calls.append(("begin-forward",))
        self.capability = (("forward_lease", "a" * 64), ("state", "forward-started"))
        return self.capability

    def apply_forward(self, capability, value, when):
        self.apply("forward", value)
        return self.mark_applied(capability, when)

    def external_rollback(self, _capability):
        self.calls.append(("external-rollback",))

    def release_rollback(self, _capability):
        self.calls.append(("release",))

    def commit_rollback(self, _capability, _guest, _proof):
        self.calls.append(("commit-rollback",))
        return "cleanup"

    def hydrate_armed(self, _capability):
        self.calls.append(("hydrate-armed",))

    def hydrate_cleanup(self, _capability):
        self.calls.append(("hydrate-cleanup",))

    def hydrate_current(self, capability):
        self.calls.append(("hydrate-current",))
        return capability

    def validate_promotion_proof(self, _proof, _capability=None):
        self.calls.append(("validate-proof",))

    def bind_target(self, _identity, _digest):
        self.calls.append(("bind-target",))
        return True

    def readback(self, expected):
        self.calls.append(("readback", expected))

    def close(self):
        self.calls.append(("close",))


def _receipt(action):
    return {
        "status": {
            "prepare": "prepared",
            "apply": "applied",
            "status": "applied",
            "confirm": "committed",
            "rollback": "rolled_back",
        }[action],
        "generation": "123e4567-e89b-42d3-a456-426614174000",
        "nonce": "a" * 64,
        "snapshot_digest": "d" * 64,
        "deadline": 2_000_000_000,
    }


def _request(tmp_path):
    identity = {
        "inventory_alias": "node-a",
        "public_service_address_sha256": hashlib.sha256(b"198.51.100.1").hexdigest(),
        "deployable_digest": "b" * 64,
    }
    return {
        "inventory_path": str(tmp_path / "inventory"),
        "inventory_name": "node-a",
        "contexts": [
            {
                "user": "deploy",
                "host": "node-a",
                "addr": "198.51.100.1",
                "laddr": "198.51.100.1",
                "lport": 22,
            },
            {
                "user": "deploy",
                "host": "node-a",
                "addr": "100.64.0.1",
                "laddr": "100.64.0.1",
                "lport": 22,
            },
        ],
        "mode": "apply",
        "promotion_config_path": str(tmp_path / "proof"),
        "target_identity": identity,
        "provider_target_sha256": "c" * 64,
    }


def test_execute_orders_public_sftp_then_tailnet_sftp_and_one_proof(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    calls = []
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "198.51.100.1",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    monkeypatch.setattr(
        m, "_bounded", lambda command, *_args, **_kwargs: calls.append(command) or b""
    )
    proof_calls = []
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 1_001,
    }
    monkeypatch.setattr(
        m, "promotion_proof", lambda *_: proof_calls.append(True) or proof
    )
    result = m.execute(
        _request(tmp_path),
        adapter,
        guest=lambda _h, action, _i, _cleanup: _receipt(action),
        known_hosts=tmp_path / "known",
    )
    assert result == {"status": "committed"} and proof_calls == [True]
    sftp_hosts = [command[-1] for command in calls if command[0] == "sftp"]
    assert sftp_hosts == ["198.51.100.1", "100.64.0.1"]


@pytest.mark.parametrize("boundary", ["invalid", "dry-run", "plan-failure"])
def test_execute_closes_adapter_on_every_preapply_boundary(
    tmp_path, monkeypatch, boundary
):
    m = mod()
    adapter = Adapter()
    request = _request(tmp_path)
    host = {
        "name": "node-a",
        "alias": "198.51.100.1",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    if boundary == "invalid":
        request.pop("provider_target_sha256")
    elif boundary == "dry-run":
        request["mode"] = "dry-run"
    else:
        adapter.plan = lambda _direction: (_ for _ in ()).throw(
            m.PromotionError("provider-plan-invalid")
        )
    if boundary == "dry-run":
        assert m.execute(
            request, adapter, guest=lambda *_: None, known_hosts=tmp_path / "known"
        ) == {"status": "dry-run"}
    else:
        with pytest.raises(m.PromotionError):
            m.execute(
                request, adapter, guest=lambda *_: None, known_hosts=tmp_path / "known"
            )
    assert adapter.calls[-1] == ("close",)


def test_execute_rolls_provider_back_before_guest_when_proof_fails(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    calls = []
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "198.51.100.1",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: b"")
    monkeypatch.setattr(m, "promotion_proof", lambda *_: None)
    original_apply = adapter.apply

    def apply(direction, value):
        calls.append(("provider", direction))
        original_apply(direction, value)

    adapter.apply = apply

    def guest(_host, action, _identity, cleanup):
        calls.append(("guest", action, cleanup))
        return _receipt(action)

    with pytest.raises(m.PromotionError, match="promotion-proof-failed"):
        m.execute(
            _request(tmp_path), adapter, guest=guest, known_hosts=tmp_path / "known"
        )
    assert calls.index(("provider", "rollback")) < calls.index(
        ("guest", "rollback", True)
    )


def test_post_forward_rollback_plan_failure_uses_armed_external_rollback_first(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "198.51.100.1",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: b"")
    original_plan = adapter.plan

    def planned(direction):
        if direction == "rollback":
            raise m.PromotionError("provider-plan-invalid")
        return original_plan(direction)

    adapter.plan = planned
    guest = []
    original_external = adapter.external_rollback
    events = []

    def external(capability):
        events.append("provider")
        original_external(capability)

    adapter.external_rollback = external
    with pytest.raises(m.PromotionError, match="provider-plan-invalid"):
        m.execute(
            _request(tmp_path),
            adapter,
            guest=lambda _h, action, _i, cleanup: events.append("guest")
            or guest.append((action, cleanup))
            or _receipt(action),
            known_hosts=tmp_path / "known",
        )
    assert events == ["guest", "provider", "guest"] and guest[-1] == ("rollback", True)


def test_prepare_refusal_closes_forward_plan_and_never_attempts_provider_rollback(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    host = {
        "name": "node-a",
        "alias": "198.51.100.1",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    with pytest.raises(m.PromotionError, match="guest-uncertain"):
        m.execute(
            _request(tmp_path),
            adapter,
            guest=lambda *_: {"status": "bad"},
            known_hosts=tmp_path / "known",
        )
    assert ("close",) in adapter.calls and ("external-rollback",) not in adapter.calls


def test_arm_failure_rolls_back_prepared_guest_without_provider_executor(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "198.51.100.1",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    adapter.arm_rollback = lambda _plan, _guest: (_ for _ in ()).throw(
        m.PromotionError("arm-failed")
    )
    guest = []
    with pytest.raises(m.PromotionError, match="arm-failed"):
        m.execute(
            _request(tmp_path),
            adapter,
            guest=lambda _h, action, _i, cleanup: guest.append((action, cleanup))
            or _receipt(action),
            known_hosts=tmp_path / "known",
        )
    assert (
        guest == [("prepare", False), ("rollback", True)]
        and ("external-rollback",) not in adapter.calls
    )


def test_write_all_retries_short_writes(monkeypatch):
    m = mod()
    read_fd, write_fd = os.pipe()
    original = m.os.write
    monkeypatch.setattr(m.os, "write", lambda fd, data: original(fd, data[:1]))
    m._write_all(write_fd, b"abc")
    os.close(write_fd)
    assert os.read(read_fd, 3) == b"abc"
    os.close(read_fd)


def test_external_rollback_arm_requires_exact_bound_receipt(tmp_path):
    m = mod()

    class Forward:
        digest = "a" * 64

        def verify(self):
            pass

    adapter = m.TerraformAdapter(
        _target(m, tmp_path), external_rollback_guard=lambda *_: {"state": "armed"}
    )
    with pytest.raises(m.PromotionError, match="provider-rollback-not-armed"):
        adapter.arm_rollback(Forward(), _receipt("prepare"))


def test_forward_lock_is_held_through_apply_marker_and_then_released(
    tmp_path, monkeypatch
):
    m = mod()
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    target = _target(m, tmp_path)
    armed = _rollback_capability(target)
    current = dict(armed)
    calls = []
    lock_path = tmp_path / "provider.lock"

    def guard(action, value):
        calls.append(action)
        if action == "begin-forward":
            current.clear()
            current.update(
                {**value, "forward_lease": "f" * 64, "state": "forward-started"}
            )
            return dict(current)
        if action == "inspect":
            return dict(current)
        if action == "mark-applied":
            current.clear()
            current.update({**value, "state": "provider-applied"})
            return dict(current)
        raise AssertionError(action)

    def provider_lock():
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    adapter = m.TerraformAdapter(
        target,
        external_rollback_guard=guard,
        provider_transaction_lock=provider_lock,
    )
    adapter._rollback_armed = True
    adapter._rollback_receipt = armed
    forward = adapter.begin_forward(armed)
    held_fd = adapter._forward_lock_fd
    os.fstat(held_fd)

    def apply(direction, _plan):
        assert direction == "forward"
        os.fstat(adapter._forward_lock_fd)
        calls.append("apply")

    monkeypatch.setattr(adapter, "apply", apply)
    marked = adapter.apply_forward(forward, object(), 999)
    assert dict(marked)["state"] == "provider-applied"
    assert adapter._forward_lock_fd == -1
    with pytest.raises(OSError):
        os.fstat(held_fd)
    assert calls == ["begin-forward", "inspect", "apply", "mark-applied"]


def test_forward_refuses_lease_that_expires_after_provider_lock(monkeypatch, tmp_path):
    m = mod()
    target = _target(m, tmp_path)
    armed = _rollback_capability(target, expires_at=1_001)
    current = dict(armed)
    monkeypatch.setattr(m.time, "time", lambda: 1_001)

    def guard(action, value):
        if action == "begin-forward":
            current.clear()
            current.update(
                {**value, "forward_lease": "f" * 64, "state": "forward-started"}
            )
            return dict(current)
        if action == "inspect":
            return dict(current)
        raise AssertionError(action)

    adapter = m.TerraformAdapter(
        target,
        external_rollback_guard=guard,
        provider_transaction_lock=lambda: os.open(
            tmp_path / "provider.lock", os.O_CREAT | os.O_RDWR, 0o600
        ),
    )
    adapter._rollback_armed = True
    adapter._rollback_receipt = armed
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        adapter.begin_forward(armed)
    assert adapter._forward_lock_fd == -1


def test_forward_refuses_lease_that_expires_immediately_before_apply(
    monkeypatch, tmp_path
):
    m = mod()
    target = _target(m, tmp_path)
    armed = _rollback_capability(target, expires_at=1_002)
    current = dict(armed)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)

    def guard(action, value):
        if action == "begin-forward":
            current.clear()
            current.update(
                {**value, "forward_lease": "f" * 64, "state": "forward-started"}
            )
            return dict(current)
        if action == "inspect":
            return dict(current)
        raise AssertionError(action)

    adapter = m.TerraformAdapter(
        target,
        external_rollback_guard=guard,
        provider_transaction_lock=lambda: os.open(
            tmp_path / "provider.lock", os.O_CREAT | os.O_RDWR, 0o600
        ),
    )
    adapter._rollback_armed = True
    adapter._rollback_receipt = armed
    forward = adapter.begin_forward(armed)
    monkeypatch.setattr(m.time, "time", lambda: 1_002)
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        adapter.apply_forward(forward, object(), 1_002)
    assert adapter._forward_lock_fd == -1


@pytest.mark.parametrize(
    "observed,identity",
    [
        (879, None),
        (1001, None),
        (
            1000,
            {
                "inventory_alias": "other",
                "public_service_address_sha256": "a" * 64,
                "deployable_digest": "b" * 64,
            },
        ),
    ],
)
def test_promotion_proof_rejects_stale_future_or_wrong_node(
    monkeypatch, observed, identity
):
    m = mod()
    expected = {
        "inventory_alias": "node-a",
        "public_service_address_sha256": "a" * 64,
        "deployable_digest": "b" * 64,
    }
    payload = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": expected if identity is None else identity,
        "observed_at": observed,
    }
    monkeypatch.setattr(m.time, "time", lambda: 1000)
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: json.dumps(payload).encode())
    assert m.promotion_proof(Path("fixture"), {}, expected, 1000) is None


def test_promotion_proof_rejects_duplicate_json_keys(monkeypatch):
    m = mod()
    expected = {
        "inventory_alias": "node-a",
        "public_service_address_sha256": "a" * 64,
        "deployable_digest": "b" * 64,
    }
    duplicate = (
        b'{"schema_version":1,"status":"passed","status":"passed",'
        b'"target_identity":{"inventory_alias":"node-a",'
        b'"public_service_address_sha256":"'
        + b"a" * 64
        + b'","deployable_digest":"'
        + b"b" * 64
        + b'"},"observed_at":1000}'
    )
    monkeypatch.setattr(m.time, "time", lambda: 1000)
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: duplicate)

    assert m.promotion_proof(Path("fixture"), {}, expected, 1000) is None


def test_release_failure_after_guest_commit_is_cleanup_debt_not_rollback(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "node-a",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 1_001,
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: b"")
    monkeypatch.setattr(m, "promotion_proof", lambda *_: proof)
    adapter.release_rollback = lambda *_: (_ for _ in ()).throw(
        m.PromotionError("release-failed")
    )
    debt = m.execute(
        _request(tmp_path),
        adapter,
        guest=lambda _h, action, _i, _cleanup: _receipt(action),
        known_hosts=tmp_path / "known",
    )
    assert (
        debt["status"] == "committed-cleanup-debt"
        and debt["rollback_capability"] == "cleanup"
    )
    assert ("apply", "rollback") not in adapter.calls


def test_current_proof_requires_post_apply_boundary(monkeypatch):
    m = mod()
    expected = {
        "inventory_alias": "node-a",
        "public_service_address_sha256": "a" * 64,
        "deployable_digest": "b" * 64,
    }
    payload = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": expected,
        "observed_at": 1001,
    }
    monkeypatch.setattr(m.time, "time", lambda: 1001)
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: json.dumps(payload).encode())
    assert m.promotion_proof(Path("fixture"), {}, expected, 1001) == payload


def test_mismatched_guest_apply_identity_rolls_provider_before_guest_rollback(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "node-a",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    calls = []

    def guest(_h, action, _i, cleanup):
        calls.append((action, cleanup))
        value = _receipt(action)
        if action == "apply":
            value["nonce"] = "c" * 64
        return value

    with pytest.raises(m.PromotionError, match="guest-uncertain"):
        m.execute(
            _request(tmp_path), adapter, guest=guest, known_hosts=tmp_path / "known"
        )
    assert ("apply", "rollback") in adapter.calls and calls[-1] == ("rollback", True)


def test_terraform_environment_is_canonical_and_sanitized():
    m = mod()
    env = m._env("p0-upcloud")
    assert env == {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PROVIDER": "upcloud",
        "ENV": "p0-upcloud",
    }
    with pytest.raises(m.PromotionError):
        m._env("unsafe/value")


def test_adapter_command_uses_reviewed_terraform_fd_through_wrapper(
    tmp_path, monkeypatch
):
    terraform = __import__("shutil").which("terraform")
    if terraform is None:
        pytest.skip("terraform unavailable")
    m = mod()
    raw = Path(terraform).read_bytes()
    fd = os.open(terraform, os.O_RDONLY)
    trusted = m.TrustedTerraform(fd, __import__("hashlib").sha256(raw).hexdigest())
    wrapper = tmp_path / "terraform-env.sh"
    wrapper.write_text('#!/bin/sh\nexec terraform "$@"\n')
    wrapper.chmod(0o700)
    monkeypatch.setattr(m, "TERRAFORM_ENV", wrapper)
    adapter = m.TerraformAdapter(_target(m, tmp_path), trusted_terraform=trusted)
    assert b"Terraform v" in adapter._command(["version"])
    os.close(fd)


def test_actual_builtin_terraform_data_plan_can_be_saved_if_terraform_exists(tmp_path):
    terraform = __import__("shutil").which("terraform")
    if terraform is None:
        pytest.skip("terraform unavailable")
    # The fixture is local-only and uses Terraform's builtin provider.
    (tmp_path / "main.tf").write_text('resource "terraform_data" "x" { input = "x" }\n')
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TF_DATA_DIR": str(tmp_path / ".tf"),
    }
    assert (
        __import__("subprocess")
        .run(
            [terraform, "init", "-backend=false"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
        )
        .returncode
        == 0
    )
    plan_path = tmp_path / "plan"
    assert (
        __import__("subprocess")
        .run(
            [terraform, "plan", "-out", str(plan_path)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
        )
        .returncode
        == 0
    )
    fd = os.open(plan_path, os.O_RDONLY)
    os.fchmod(fd, 0o600)
    inode = os.fstat(fd).st_ino
    os.unlink(plan_path)
    saved = mod().SavedPlan(fd)
    assert os.fstat(saved.fd).st_ino == inode
    fd_path = saved.path()
    shown = __import__("subprocess").run(
        [terraform, "show", "-json", fd_path],
        cwd=tmp_path,
        env=env,
        pass_fds=(fd,),
        capture_output=True,
    )
    assert shown.returncode == 0 and json.loads(shown.stdout)[
        "format_version"
    ].startswith("1.")
    applied = __import__("subprocess").run(
        [terraform, "apply", "-auto-approve", fd_path],
        cwd=tmp_path,
        env=env,
        pass_fds=(fd,),
        capture_output=True,
    )
    assert applied.returncode == 0
    saved.close()


def test_provider_target_binds_exact_state_environment_node_and_open_inode(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    request = _request(tmp_path)
    request["provider_target_sha256"] = target.digest
    host = {
        "name": "node-a",
        "alias": "node-a",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    adapter = m.TerraformAdapter(target)
    with pytest.raises(m.PromotionError, match="terraform-executable-not-trusted"):
        m.execute(
            request, adapter, guest=lambda *_: None, known_hosts=tmp_path / "known"
        )
    assert adapter._plans == set()

    other = _target(m, tmp_path, alias="node-b", environment="other")
    mismatch = m.TerraformAdapter(other)
    with pytest.raises(m.PromotionError, match="provider-target-mismatch"):
        m.execute(
            request, mismatch, guest=lambda *_: None, known_hosts=tmp_path / "known"
        )
    assert mismatch._plans == set()


def test_provider_target_rejects_tamper_and_state_drift_before_plan(
    tmp_path, monkeypatch
):
    m = mod()
    path = tmp_path / "provider-target-node-a.json"
    target = _target(m, tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(m.PromotionError, match="provider-target-invalid"):
        target.verify()

    target = _target(m, tmp_path / "fresh")
    adapter = m.TerraformAdapter(target)
    monkeypatch.setattr(adapter, "_command", lambda *_a, **_k: b'{"serial":2}\n')
    with pytest.raises(m.PromotionError, match="provider-state-drift"):
        adapter.plan("forward")


def test_provider_target_derives_uuid_and_public_address_from_exact_state(tmp_path):
    m = mod()
    bad_state = (
        json.dumps(
            {
                "version": 4,
                "outputs": {"server_ipv4": {"value": "203.0.113.9"}},
                "resources": [
                    {
                        "mode": "managed",
                        "type": "upcloud_server",
                        "name": "vpn",
                        "instances": [{"attributes": {"id": SERVER}}],
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    with pytest.raises(m.PromotionError, match="provider-target-invalid"):
        _target(m, tmp_path, state=bad_state)


def _rollback_capability(target, *, expires_at=2_000):
    return tuple(
        sorted(
            {
                "server_uuid": SERVER,
                "environment": "staging",
                "provider_target_sha256": target.digest,
                "forward_plan_sha256": "a" * 64,
                "guest_generation": "123e4567-e89b-42d3-a456-426614174000",
                "guest_nonce": "a" * 64,
                "guest_snapshot_digest": "d" * 64,
                "guest_deadline": 2_000_000_000,
                "expires_at": expires_at,
                "state": "armed",
            }.items()
        )
    )


def _cleanup_capability(target, *, expires_at=2_000):
    value = dict(_rollback_capability(target, expires_at=expires_at))
    value |= {
        "state": "committed-cleanup-debt",
        "forward_lease": "f" * 64,
        "provider_applied_at": 999,
        "promotion_observed_at": 1_000,
    }
    return tuple(sorted(value.items()))


def _applied_capability(target, *, expires_at=2_000):
    value = dict(_rollback_capability(target, expires_at=expires_at))
    value |= {
        "state": "provider-applied",
        "forward_lease": "f" * 64,
        "provider_applied_at": 999,
    }
    return tuple(sorted(value.items()))


def test_cleanup_debt_rehydrates_on_fresh_adapter_and_releases(tmp_path, monkeypatch):
    m = mod()
    target = _target(m, tmp_path)
    capability = _cleanup_capability(target)
    calls = []

    def guard(action, value):
        calls.append(action)
        if action == "inspect":
            return value
        if action == "release":
            return {"state": "released"}
        raise AssertionError(action)

    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    fresh = m.TerraformAdapter(target, external_rollback_guard=guard)
    assert m.reconcile_release(fresh, capability) == {"status": "committed"}
    assert calls == ["inspect", "release"] and fresh._rollback_armed is False


@pytest.mark.parametrize("mutation", ["missing", "tampered", "expired"])
def test_cleanup_debt_rehydrate_refuses_missing_tampered_or_expired(
    tmp_path, monkeypatch, mutation
):
    m = mod()
    target = _target(m, tmp_path)
    capability = dict(_cleanup_capability(target))
    if mutation == "missing":
        capability.pop("forward_plan_sha256")
    elif mutation == "tampered":
        capability["server_uuid"] = "223e4567-e89b-42d3-a456-426614174000"
    else:
        capability["expires_at"] = 999
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    adapter = m.TerraformAdapter(target, external_rollback_guard=lambda *_: capability)
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        m.reconcile_release(adapter, tuple(sorted(capability.items())))
    assert adapter._rollback_armed is False


def test_cleanup_debt_release_failure_retains_rehydrated_capability(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    capability = _cleanup_capability(target)
    monkeypatch.setattr(m.time, "time", lambda: 1_000)

    def guard(action, value):
        if action == "inspect":
            return value
        return {"state": "still-armed"}

    adapter = m.TerraformAdapter(target, external_rollback_guard=guard)
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        m.reconcile_release(adapter, capability)
    assert adapter._rollback_armed is False and adapter._cleanup_receipt == capability


def test_final_provider_readback_failure_prevents_confirm_and_rolls_provider_first(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "node-a",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: b"")
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 1_001,
    }
    monkeypatch.setattr(m, "promotion_proof", lambda *_: proof)
    events = []
    original_apply = adapter.apply

    def apply(direction, value):
        events.append(("provider", direction))
        original_apply(direction, value)

    adapter.apply = apply
    adapter.readback = lambda _expected: (_ for _ in ()).throw(
        m.PromotionError("provider-readback-invalid")
    )

    def guest(_host, action, _identity, cleanup):
        events.append(("guest", action, cleanup))
        return _receipt(action)

    with pytest.raises(m.PromotionError, match="provider-readback-invalid"):
        m.execute(
            _request(tmp_path), adapter, guest=guest, known_hosts=tmp_path / "known"
        )
    assert not any(event[0] == "guest" and event[1] == "confirm" for event in events)
    assert ("release",) not in adapter.calls
    assert events.index(("provider", "rollback")) < events.index(
        ("guest", "rollback", True)
    )


def test_rollback_plan_and_apply_use_post_forward_readback_not_initial_state_digest(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    adapter = m.TerraformAdapter(
        target,
        return_path_guard=lambda *_: None,
        external_rollback_guard=lambda *_: None,
        allow_apply=True,
    )
    monkeypatch.setattr(
        adapter,
        "_verify_initial_state",
        lambda: (_ for _ in ()).throw(AssertionError("initial state is obsolete")),
    )
    readbacks = []
    monkeypatch.setattr(
        adapter, "_readback", lambda expected: readbacks.append(expected)
    )

    def command(arguments, **_kwargs):
        if arguments[0] == "plan":
            output = Path(arguments[arguments.index("-out") + 1])
            output.write_bytes(b"plan")
            output.chmod(0o600)
            return b""
        if arguments[0] == "show":
            return plan(True, False)
        if arguments[0] == "apply":
            return b""
        raise AssertionError(arguments)

    monkeypatch.setattr(adapter, "_command", command)
    rollback = adapter.plan("rollback")
    adapter._rollback_armed = True
    adapter.apply("rollback", rollback)
    assert readbacks == [True, True, False]


def test_reconcile_release_refuses_preconfirm_armed_capability(tmp_path, monkeypatch):
    m = mod()
    target = _target(m, tmp_path)
    armed = _rollback_capability(target)
    calls = []

    def guard(action, value):
        calls.append(action)
        return value

    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    adapter = m.TerraformAdapter(target, external_rollback_guard=guard)
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        m.reconcile_release(adapter, armed)
    assert (
        calls == []
        and adapter._rollback_armed is False
        and adapter._cleanup_receipt is None
    )


def test_postconfirm_restart_transitions_armed_to_cleanup_debt_then_releases(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    armed = _rollback_capability(target)
    applied = _applied_capability(target)
    guest = _receipt("confirm")
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 1_000,
    }
    calls = []

    def guard(action, value):
        calls.append(action)
        if action == "inspect-current":
            return dict(applied)
        if action == "inspect":
            return value
        if action == "commit":
            return {**value, "state": "committed-cleanup-debt"}
        if action == "release":
            return {"state": "released"}
        raise AssertionError(action)

    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    adapter = m.TerraformAdapter(target, external_rollback_guard=guard)
    assert m.reconcile_commit_release(adapter, armed, guest, proof) == {
        "status": "committed"
    }
    assert calls == ["inspect-current", "inspect", "commit", "release"]
    assert adapter._rollback_armed is False and adapter._cleanup_receipt is None


def test_restart_refuses_foreign_committed_guest_before_guard_commit(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    armed = _rollback_capability(target)
    applied = _applied_capability(target)
    foreign = _receipt("confirm")
    foreign["nonce"] = "b" * 64
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 1_000,
    }
    calls = []

    def guard(action, value):
        calls.append(action)
        if action == "inspect-current":
            return dict(applied)
        if action == "inspect":
            return value
        raise AssertionError(action)

    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    adapter = m.TerraformAdapter(target, external_rollback_guard=guard)
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        m.reconcile_commit_release(adapter, armed, foreign, proof)
    assert calls == ["inspect-current", "inspect"]


def test_restart_after_guard_commit_lost_response_rehydrates_cleanup_and_releases(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    armed = _rollback_capability(target)
    cleanup = _cleanup_capability(target)
    guest = _receipt("confirm")
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 1_000,
    }
    calls = []

    def guard(action, value):
        calls.append(action)
        if action == "inspect-current":
            return dict(cleanup)
        if action == "inspect":
            return value
        if action == "release":
            return {"state": "released"}
        raise AssertionError(action)

    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    adapter = m.TerraformAdapter(target, external_rollback_guard=guard)
    assert m.reconcile_commit_release(adapter, armed, guest, proof) == {
        "status": "committed"
    }
    assert calls == ["inspect-current", "inspect", "release"]
    assert adapter._cleanup_receipt is None


def test_restart_refuses_proof_older_than_durable_provider_apply_marker(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    armed = _rollback_capability(target)
    applied = dict(_applied_capability(target))
    applied["provider_applied_at"] = 1_000
    applied = tuple(sorted(applied.items()))
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 999,
    }
    calls = []

    def guard(action, value):
        calls.append(action)
        if action == "inspect-current":
            return dict(applied)
        if action == "inspect":
            return value
        raise AssertionError(action)

    monkeypatch.setattr(m.time, "time", lambda: 1_001)
    adapter = m.TerraformAdapter(target, external_rollback_guard=guard)
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        m.reconcile_commit_release(adapter, armed, _receipt("confirm"), proof)
    assert calls == ["inspect-current", "inspect"]


def test_arm_and_reconcile_refuse_expired_guest_deadline(tmp_path, monkeypatch):
    m = mod()
    target = _target(m, tmp_path)
    calls = []
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    adapter = m.TerraformAdapter(
        target, external_rollback_guard=lambda action, value: calls.append(action)
    )

    class Forward:
        digest = "a" * 64

        def verify(self):
            pass

    expired = _receipt("prepare")
    expired["deadline"] = 999
    with pytest.raises(m.PromotionError, match="guest-uncertain"):
        adapter.arm_rollback(Forward(), expired)
    assert calls == []

    applied = dict(_applied_capability(target))
    applied["guest_deadline"] = 999
    applied = tuple(sorted(applied.items()))
    adapter = m.TerraformAdapter(
        target, external_rollback_guard=lambda action, value: value
    )
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        m.reconcile_commit_release(
            adapter,
            _rollback_capability(target),
            {**_receipt("confirm"), "deadline": 999},
            {
                "schema_version": 1,
                "status": "passed",
                "target_identity": _request(tmp_path)["target_identity"],
                "observed_at": 998,
            },
        )


def test_adapter_close_owns_target_and_trusted_executable_fds(tmp_path):
    m = mod()
    target = _target(m, tmp_path)
    executable = tmp_path / "terraform"
    executable.write_bytes(b"fixture")
    executable.chmod(0o700)
    trusted_fd = os.open(executable, os.O_RDONLY)
    trusted = m.TrustedTerraform(trusted_fd, hashlib.sha256(b"fixture").hexdigest())
    target_fds = (target.fd, target.state_fd)
    adapter = m.TerraformAdapter(target, trusted_terraform=trusted)
    adapter.close()
    adapter.close()
    for fd in (*target_fds, trusted_fd):
        with pytest.raises(OSError):
            os.fstat(fd)


def test_guest_confirm_followed_by_external_commit_failure_retains_armed_lease(
    tmp_path, monkeypatch
):
    m = mod()
    adapter = Adapter()
    (tmp_path / "known").write_text("fixture")
    host = {
        "name": "node-a",
        "alias": "node-a",
        "address": "198.51.100.1",
        "transport": "100.64.0.1",
        "port": 22,
        "key": "k",
        "user": "deploy",
    }
    monkeypatch.setattr(m.fleet_inspection, "select_hosts", lambda *_: [host])
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: b"")
    proof = {
        "schema_version": 1,
        "status": "passed",
        "target_identity": _request(tmp_path)["target_identity"],
        "observed_at": 1_001,
    }
    monkeypatch.setattr(m, "promotion_proof", lambda *_: proof)
    adapter.commit_rollback = lambda *_: (_ for _ in ()).throw(
        m.PromotionError("commit-failed")
    )
    result = m.execute(
        _request(tmp_path),
        adapter,
        guest=lambda _h, action, _i, _cleanup: _receipt(action),
        known_hosts=tmp_path / "known",
    )
    assert result["status"] == "committed-rollback-armed"
    assert result["rollback_capability"] == adapter.capability
    assert ("release",) not in adapter.calls and (
        "apply",
        "rollback",
    ) not in adapter.calls


def test_real_adapter_final_false_uses_external_executor_then_guest_rollback(
    tmp_path, monkeypatch
):
    m = mod()
    target = _target(m, tmp_path)
    events = []
    (tmp_path / "known").write_text("fixture\n")
    (tmp_path / "known").chmod(0o644)

    def return_guard(action, value):
        if action == "forward":
            return True
        if action == "readback":
            return {**value, "firewall": False}
        raise AssertionError(action)

    def external_guard(action, value):
        events.append(("guard", action))
        if action == "arm":
            return {**value, "expires_at": 2_000, "state": "armed"}
        if action == "begin-forward":
            return {**value, "forward_lease": "a" * 64, "state": "forward-started"}
        if action == "mark-applied":
            return {**value, "state": "provider-applied"}
        if action == "execute":
            return {"state": "executed"}
        raise AssertionError(action)

    adapter = m.TerraformAdapter(
        target,
        return_path_guard=return_guard,
        external_rollback_guard=external_guard,
        allow_apply=True,
    )

    class Plan:
        digest = "e" * 64

        def verify(self):
            pass

        def close(self):
            pass

    def planned(direction):
        value = Plan()
        adapter._plans.add(value)
        events.append(("plan", direction))
        return value

    adapter.plan = planned
    original_apply = adapter.apply

    def applied(direction, value):
        events.append(("apply", direction))
        if direction == "forward":
            adapter._plans.discard(value)
            return None
        return original_apply(direction, value)

    adapter.apply = applied
    monkeypatch.setattr(m.time, "time", lambda: 1_000)
    monkeypatch.setattr(
        m.fleet_inspection,
        "select_hosts",
        lambda *_: [
            {
                "name": "node-a",
                "alias": "node-a",
                "address": "198.51.100.1",
                "transport": "100.64.0.1",
                "port": 22,
                "key": "k",
                "user": "deploy",
            }
        ],
    )
    monkeypatch.setattr(m, "_bounded", lambda *_a, **_k: b"")
    monkeypatch.setattr(
        m,
        "promotion_proof",
        lambda *_: {
            "schema_version": 1,
            "status": "passed",
            "target_identity": _request(tmp_path)["target_identity"],
            "observed_at": 1_001,
        },
    )
    guest_events = []

    def guest(_host, action, _identity, cleanup):
        guest_events.append((action, cleanup))
        return _receipt(action)

    request = _request(tmp_path)
    request["provider_target_sha256"] = target.digest
    with pytest.raises(m.PromotionError, match="rollback-uncertain"):
        m.execute(request, adapter, guest=guest, known_hosts=tmp_path / "known")
    assert ("guard", "execute") in events
    assert guest_events[-1] == ("rollback", True)
    assert not any(action == "confirm" for action, _ in guest_events)
