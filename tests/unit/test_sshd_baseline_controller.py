"""Controller ordering fixtures; they are not live SSH or VPN evidence."""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def module():
    spec = importlib.util.spec_from_file_location(
        "sshd_baseline_controller", ROOT / "scripts/sshd-baseline-controller.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def transaction_request(tmp_path):
    key = tmp_path / "key"
    key.write_text("fixture")
    key.chmod(0o600)
    inventory = tmp_path / "inventory.ini"
    inventory.write_text(
        "[vpn]\nnode-a ansible_host=192.0.2.10 ansible_user=deploy ansible_port=2222 "
        "inspection_transport_host=100.64.0.10 inspection_host_key_alias=192.0.2.10\n"
        "[vpn:vars]\nansible_ssh_private_key_file=" + str(key) + "\n"
    )
    known = tmp_path / "known_hosts"
    known.write_text("fixture-pin")
    proof = tmp_path / "proof.yaml"
    proof.write_text("{}")
    proof.chmod(0o600)
    receipts = tmp_path / "receipts"
    receipts.mkdir(mode=0o700)
    receipt_parent = receipts.stat()
    return {
        "schema_version": 2, "mode": "deploy", "inventory_alias": "node-a",
        "inventory_path": str(inventory), "known_hosts_path": str(known),
        "contexts": [
            {"user": "deploy", "host": "controller-a", "addr": "198.51.100.2",
             "laddr": "192.0.2.10", "lport": 2222},
            {"user": "deploy", "host": "controller-a", "addr": "100.64.0.2",
             "laddr": "100.64.0.10", "lport": 2222},
        ],
        "hardening_b64": base64.b64encode(b"X11Forwarding no\nSubsystem sftp internal-sftp\n").decode(),
        "bundle_generation": "a" * 64, "timeout_seconds": 180,
        "promotion_config_path": str(proof),
        "failure_receipt_path": str(receipts / "failure.json"),
        "failure_receipt_parent_identity": {
            "device": receipt_parent.st_dev,
            "inode": receipt_parent.st_ino,
        },
        "target_identity": {"inventory_alias": "node-a", "public_service_address_sha256": "b" * 64,
                            "deployable_digest": "c" * 64},
    }


def receipt(status):
    return {"generation": "00000000-0000-4000-8000-000000000001", "nonce": "d" * 64,
            "status": status, "deadline": 999, "snapshot_digest": "e" * 64}


def proof_receipt(request, observed_at=101):
    return {"schema_version": 1, "status": "passed",
            "target_identity": request["target_identity"], "observed_at": observed_at}


def test_deploy_orders_apply_fresh_public_and_management_proofs_before_confirm(transaction_request):
    controller = module()
    calls = []

    def rpc(host, known, action, payload, environment, cleanup=False):
        calls.append(("rpc", host["transport"], action, cleanup))
        return receipt({"prepare": "prepared", "apply": "applied", "status": (
            "committed" if sum(1 for call in calls if call[2] == "confirm") else "applied"),
            "confirm": "committed", "rollback": "rolled_back"}[action])

    def sftp(host, known, environment):
        calls.append(("sftp", host["transport"], "proof", False))

    def proof(root, path, environment):
        calls.append(("proof", "local", "promotion", False))
        return proof_receipt(transaction_request)

    assert controller.execute(transaction_request, {}, rpc=rpc, sftp=sftp, proof=proof, clock=lambda: 100) == {
        "status": "committed"}
    assert calls == [
        ("rpc", "100.64.0.10", "prepare", False),
        ("rpc", "100.64.0.10", "apply", False),
        ("rpc", "192.0.2.10", "status", False),
        ("sftp", "192.0.2.10", "proof", False),
        ("rpc", "100.64.0.10", "status", False),
        ("sftp", "100.64.0.10", "proof", False),
        ("proof", "local", "promotion", False),
        ("rpc", "100.64.0.10", "status", False),
        ("rpc", "100.64.0.10", "confirm", False),
        ("rpc", "100.64.0.10", "status", False),
    ]


def test_check_mode_only_previews_and_creates_no_promotion_dependency(transaction_request):
    controller = module()
    transaction_request = dict(transaction_request, mode="check", promotion_config_path=None,
                               failure_receipt_path=None, failure_receipt_parent_identity=None)
    calls = []

    def rpc(host, known, action, payload, environment, cleanup=False):
        calls.append((action, payload))
        return {"status": "would-change", "snapshot_digest": "f" * 64}

    assert controller.execute(transaction_request, {}, rpc=rpc) == {"status": "would-change"}
    assert len(calls) == 1 and calls[0][0] == "prepare" and calls[0][1]["check_mode"] is True


@pytest.mark.parametrize("mutation", ["missing-management", "wrong-port", "missing-local-address"])
def test_transport_context_binding_refuses_before_prepare(transaction_request, mutation):
    controller = module()
    value = json.loads(json.dumps(transaction_request))
    if mutation == "missing-management":
        path = Path(value["inventory_path"])
        path.write_text(path.read_text().replace(
            " inspection_transport_host=100.64.0.10 inspection_host_key_alias=192.0.2.10", ""))
    elif mutation == "wrong-port":
        for context in value["contexts"]:
            context["lport"] = 22
    else:
        value["contexts"][1]["laddr"] = "192.0.2.10"
    called = False
    def rpc(*args, **kwargs):
        nonlocal called
        called = True
    with pytest.raises(controller.BaselineError, match="management-transport-required"):
        controller.execute(value, {}, rpc=rpc)
    assert not called


@pytest.mark.parametrize("failure", ["apply", "public-status", "public-sftp", "management-status",
                                      "management-sftp", "promotion", "preconfirm-status", "confirm"])
def test_every_post_prepare_failure_attempts_one_bounded_rollback(transaction_request, failure):
    controller = module()
    calls = []
    statuses = 0

    def rpc(host, known, action, payload, environment, cleanup=False):
        nonlocal statuses
        calls.append((action, cleanup))
        if action == "status":
            statuses += 1
            label = {1: "public-status", 2: "management-status", 3: "preconfirm-status"}.get(statuses)
            if failure == label:
                raise controller.BaselineError("fixture")
        if action == failure:
            raise controller.BaselineError("fixture")
        return receipt({"prepare": "prepared", "apply": "applied", "status": "applied",
                        "confirm": "committed", "rollback": "rolled_back"}[action])

    sftp_count = 0
    def sftp(host, known, environment):
        nonlocal sftp_count
        sftp_count += 1
        if failure == ("public-sftp" if sftp_count == 1 else "management-sftp"):
            raise controller.BaselineError("fixture")

    def proof(root, path, environment):
        if failure == "promotion":
            raise controller.BaselineError("fixture")
        return proof_receipt(transaction_request)

    with pytest.raises(controller.BaselineError):
        controller.execute(transaction_request, {}, rpc=rpc, sftp=sftp, proof=proof, clock=lambda: 100)
    assert calls.count(("rollback", True)) == 1
    assert "confirm" not in [call[0] for call in calls] or failure == "confirm"


@pytest.mark.parametrize("mutation", ["status", "extra", "observed", "identity"])
def test_promotion_receipt_parser_requires_exact_safe_schema(transaction_request, mutation, monkeypatch):
    controller = module()
    value = proof_receipt(transaction_request)
    if mutation == "status":
        value["status"] = "ok"
    elif mutation == "extra":
        value["detail"] = "unsafe"
    elif mutation == "observed":
        value["observed_at"] = True
    else:
        value["target_identity"] = {**value["target_identity"], "extra": "unsafe"}
    monkeypatch.setattr(controller, "run_command", lambda *args, **kwargs: (0, json.dumps(value)))
    with pytest.raises(controller.BaselineError, match="promotion-proof-failed"):
        controller.promotion_proof(ROOT, Path(transaction_request["promotion_config_path"]), {})


def test_promotion_receipt_parser_accepts_exact_safe_schema(transaction_request, monkeypatch):
    controller = module()
    value = proof_receipt(transaction_request)
    monkeypatch.setattr(controller, "run_command", lambda *args, **kwargs: (0, json.dumps(value)))
    assert controller.promotion_proof(
        ROOT, Path(transaction_request["promotion_config_path"]), {}) == value


def test_promotion_proof_uses_the_controller_environment(transaction_request, monkeypatch):
    controller = module()
    value = proof_receipt(transaction_request)
    observed = {}

    def run_command(*args, **kwargs):
        observed["environment"] = kwargs.get("environment")
        return 0, json.dumps(value)

    monkeypatch.setattr(controller, "run_command", run_command)
    environment = {"PATH": "/usr/bin:/bin", "HOME": "/private/tmp", "LANG": "C", "LC_ALL": "C"}
    assert controller.promotion_proof(
        ROOT, Path(transaction_request["promotion_config_path"]), environment) == value
    assert observed["environment"] is environment


@pytest.mark.parametrize("mutation", ["stale", "wrong-target"])
def test_promotion_binding_mismatch_rolls_back_before_confirm(transaction_request, mutation):
    controller = module()
    calls = []

    def rpc(host, known, action, payload, environment, cleanup=False):
        calls.append((action, cleanup))
        return receipt({"prepare": "prepared", "apply": "applied", "status": "applied",
                        "confirm": "committed", "rollback": "rolled_back"}[action])

    def proof(root, path, environment):
        value = proof_receipt(transaction_request, observed_at=99 if mutation == "stale" else 101)
        if mutation == "wrong-target":
            value["target_identity"] = {**value["target_identity"], "deployable_digest": "f" * 64}
        return value

    with pytest.raises(controller.BaselineError, match="promotion-proof-mismatch"):
        controller.execute(transaction_request, {}, rpc=rpc, sftp=lambda *args: None,
                           proof=proof, clock=lambda: 100)
    assert calls.count(("rollback", True)) == 1
    assert not any(action == "confirm" for action, _cleanup in calls)


def test_same_second_pre_apply_observation_rolls_back(transaction_request):
    controller = module()
    calls = []

    def rpc(host, known, action, payload, environment, cleanup=False):
        calls.append((action, cleanup))
        return receipt({"prepare": "prepared", "apply": "applied", "status": "applied",
                        "confirm": "committed", "rollback": "rolled_back"}[action])

    with pytest.raises(controller.BaselineError, match="promotion-proof-mismatch"):
        controller.execute(transaction_request, {}, rpc=rpc, sftp=lambda *args: None,
                           proof=lambda *args: proof_receipt(transaction_request, observed_at=100),
                           clock=lambda: 100.9)
    assert calls.count(("rollback", True)) == 1


def test_transaction_budget_accepts_only_the_shared_upper_bound(transaction_request):
    controller = module()
    value = dict(transaction_request, timeout_seconds=controller.TRANSACTION_TIMEOUT_SECONDS)
    assert controller.validate_request(value)["timeout_seconds"] == 960
    with pytest.raises(controller.BaselineError, match="request-invalid"):
        controller.validate_request(dict(value, timeout_seconds=961))


def test_cancellation_still_gets_one_deferred_cleanup_rpc(transaction_request):
    controller = module()
    calls = []

    def rpc(host, known, action, payload, environment, cleanup=False):
        calls.append((action, cleanup))
        if action == "apply":
            raise SystemExit(143)
        return receipt("prepared" if action == "prepare" else "rolled_back")

    with pytest.raises(SystemExit):
        controller.execute(transaction_request, {}, rpc=rpc)
    assert calls == [("prepare", False), ("apply", False), ("rollback", True)]


def test_uncertain_rollback_is_a_distinct_fail_closed_result(transaction_request):
    controller = module()

    def rpc(host, known, action, payload, environment, cleanup=False):
        if action in {"apply", "rollback"}:
            raise controller.BaselineError("fixture")
        return receipt("prepared")

    with pytest.raises(controller.BaselineError, match="rollback-uncertain-recovery-armed"):
        controller.execute(transaction_request, {}, rpc=rpc)


@pytest.mark.parametrize("mutation", ["unknown-alias", "bad-generation", "one-context",
                                       "proof-in-check", "missing-proof-in-deploy"])
def test_request_boundaries_fail_before_rpc(transaction_request, mutation):
    controller = module()
    value = json.loads(json.dumps(transaction_request))
    if mutation == "unknown-alias":
        value["inventory_alias"] = "node-b"
        value["target_identity"]["inventory_alias"] = "node-b"
    elif mutation == "bad-generation":
        value["bundle_generation"] = "x"
    elif mutation == "one-context":
        value["contexts"] = value["contexts"][:1]
    elif mutation == "proof-in-check":
        value["mode"] = "check"
    else:
        value["promotion_config_path"] = None
    called = False
    def rpc(*args, **kwargs):
        nonlocal called
        called = True
    with pytest.raises((controller.BaselineError, controller.fleet_inspection.InspectionError)):
        controller.execute(value, {}, rpc=rpc)
    assert not called


def test_disposable_first_onboarding_and_fresh_proof_precede_unchanged_prepare(transaction_request):
    controller = module()
    calls = []
    final = Path(transaction_request["promotion_config_path"]).with_name("final.json")

    def onboard(path, environment):
        calls.append("onboard")
        return final, True

    def proof(root, path, environment):
        assert path == final
        calls.append("proof")
        return proof_receipt(transaction_request)

    def rpc(*args, **kwargs):
        calls.append("prepare")
        return {"status": "unchanged"}

    assert controller.execute(transaction_request, {}, onboard=onboard, proof=proof,
                              rpc=rpc, clock=lambda: 100) == {"status": "unchanged"}
    assert calls == ["onboard", "proof", "prepare"]


@pytest.mark.parametrize("failure", ["onboard", "proof", "stale", "identity"])
def test_onboarding_failure_never_arms_ssh_transaction(transaction_request, failure):
    controller = module()
    calls = []

    def onboard(path, environment):
        if failure == "onboard":
            raise controller.BaselineError("onboarding-refused")
        return path, True

    def proof(*args):
        if failure == "proof":
            raise controller.BaselineError("proof-refused")
        result = proof_receipt(transaction_request, observed_at=99 if failure == "stale" else 101)
        if failure == "identity":
            result["target_identity"] = {}
        return result

    with pytest.raises(controller.BaselineError):
        controller.execute(transaction_request, {}, onboard=onboard, proof=proof,
                           rpc=lambda *a, **k: calls.append("rpc"), clock=lambda: 100)
    assert calls == []


def test_check_mode_does_not_read_or_finalize_onboarding_capability(transaction_request):
    controller = module()
    request = dict(transaction_request, mode="check", promotion_config_path=None,
                   failure_receipt_path=None, failure_receipt_parent_identity=None)
    def forbidden(*args):
        pytest.fail("check mode must not read onboarding inputs or launch evaluator")
    result = controller.execute(request, {}, onboard=forbidden, proof=forbidden,
        rpc=lambda *a, **k: {"status": "unchanged", "snapshot_digest": "e" * 64})
    assert result == {"status": "unchanged"}


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("secret-address=192.0.2.10", "controller-failure"),
        ("prepare-rpc-failed", "prepare-rpc-failed"),
    ],
)
def test_handled_failure_publishes_only_allowlisted_private_category(
        transaction_request, detail, expected):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])

    def rpc(*args, **kwargs):
        raise controller.BaselineError(detail)

    with pytest.raises(controller.BaselineError, match=detail):
        controller.execute(transaction_request, {}, rpc=rpc)
    assert json.loads(path.read_bytes()) == {
        "schema_version": 1,
        "status": "failed",
        "reason": expected,
    }
    assert path.stat().st_mode & 0o777 == 0o600
    assert b"192.0.2.10" not in path.read_bytes()


def test_safe_sink_validation_failure_publishes_before_rpc(transaction_request):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])
    request = dict(transaction_request, target_identity={})

    def forbidden(*args, **kwargs):
        pytest.fail("invalid request must refuse before RPC")

    with pytest.raises(controller.BaselineError, match="request-invalid"):
        controller.execute(request, {}, rpc=forbidden)
    assert json.loads(path.read_bytes()) == {
        "schema_version": 1,
        "status": "failed",
        "reason": "controller-failure",
    }
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), SystemExit(130)])
def test_interruption_after_prepare_rolls_back_and_publishes(
        transaction_request, interruption):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])
    calls = []

    def rpc(host, known, action, request, environment, cleanup=False):
        calls.append((action, cleanup))
        if action == "prepare":
            return receipt("prepared")
        if action == "apply":
            raise interruption
        assert action == "rollback"
        return receipt("rolled_back")

    with pytest.raises(type(interruption)) as raised:
        controller.execute(transaction_request, {}, rpc=rpc)
    if isinstance(interruption, SystemExit):
        assert raised.value.code == 130
    assert calls == [("prepare", False), ("apply", False), ("rollback", True)]
    assert json.loads(path.read_bytes()) == {
        "schema_version": 1,
        "status": "failed",
        "reason": "controller-failure",
    }


def test_success_and_check_mode_leave_failure_receipt_absent(transaction_request):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])
    assert controller.execute(
        transaction_request, {}, rpc=lambda *args, **kwargs: {"status": "unchanged"},
        proof=lambda *args: proof_receipt(transaction_request), onboard=lambda path, env: (path, False),
    ) == {"status": "unchanged"}
    assert not path.exists()

    check = dict(transaction_request, mode="check", promotion_config_path=None,
                 failure_receipt_path=None, failure_receipt_parent_identity=None)
    assert controller.execute(
        check, {}, rpc=lambda *args, **kwargs: {"status": "unchanged", "snapshot_digest": "f" * 64},
    ) == {"status": "unchanged"}
    assert not path.exists()


@pytest.mark.parametrize("case", ["existing", "symlink", "unsafe-parent"])
def test_unsafe_failure_receipt_refuses_before_rpc(transaction_request, case):
    controller = module()
    value = dict(transaction_request)
    path = Path(value["failure_receipt_path"])
    if case == "existing":
        path.write_text("foreign")
    elif case == "symlink":
        target = path.parent.with_name("other-receipts")
        target.mkdir(mode=0o700)
        path.parent.rmdir()
        path.parent.symlink_to(target, target_is_directory=True)
    else:
        path.parent.chmod(0o755)
    called = False

    def rpc(*args, **kwargs):
        nonlocal called
        called = True

    with pytest.raises(controller.BaselineError, match="request-invalid"):
        controller.execute(value, {}, rpc=rpc)
    assert not called
    if case == "existing":
        assert path.read_text() == "foreign"


def test_parent_replacement_cannot_receive_or_mask_failure_receipt(transaction_request):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])
    original_parent = path.parent.with_name("original-receipts")

    def onboard(*args):
        path.parent.rename(original_parent)
        path.parent.mkdir(mode=0o700)
        raise controller.BaselineError("onboarding-refused")

    with pytest.raises(controller.BaselineError, match="onboarding-refused"):
        controller.execute(transaction_request, {}, onboard=onboard)
    assert not path.exists()
    assert not (original_parent / path.name).exists()


def test_final_path_creation_race_is_not_overwritten_or_masked(transaction_request):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])

    def onboard(*args):
        path.write_bytes(b"foreign-private-state\n")
        path.chmod(0o600)
        raise controller.BaselineError("onboarding-refused")

    with pytest.raises(controller.BaselineError, match="onboarding-refused"):
        controller.execute(transaction_request, {}, onboard=onboard)
    assert path.read_bytes() == b"foreign-private-state\n"


def test_final_path_race_after_prepare_preserves_failure_and_foreign_file(transaction_request):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])
    calls = []

    def rpc(host, known, action, request, environment, cleanup=False):
        calls.append((action, cleanup))
        if action == "prepare":
            return receipt("prepared")
        if action == "apply":
            path.write_bytes(b"foreign-private-state\n")
            path.chmod(0o600)
            raise controller.BaselineError("apply-rpc-failed")
        assert action == "rollback"
        return receipt("rolled_back")

    with pytest.raises(controller.BaselineError, match="apply-rpc-failed"):
        controller.execute(transaction_request, {}, rpc=rpc)
    assert calls == [("prepare", False), ("apply", False), ("rollback", True)]
    assert path.read_bytes() == b"foreign-private-state\n"


def test_main_keeps_public_failure_generic_while_private_receipt_is_redacted(
        transaction_request, monkeypatch, capsys):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])
    monkeypatch.setattr(controller, "_request", lambda: transaction_request)
    monkeypatch.setattr(
        controller,
        "_execute_validated",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            controller.BaselineError("private-address=192.0.2.10")
        ),
    )
    assert controller.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "reason": "ssh-baseline-transaction-failed",
    }
    assert json.loads(path.read_bytes()) == {
        "schema_version": 1,
        "status": "failed",
        "reason": "controller-failure",
    }


@pytest.mark.parametrize(
    ("interruption", "expected_status"),
    [(KeyboardInterrupt(), 130), (SystemExit(75), 75), (SystemExit(0), 1)],
)
def test_main_keeps_handled_interrupt_public_failure_generic(
        transaction_request, monkeypatch, capsys, interruption, expected_status):
    controller = module()
    path = Path(transaction_request["failure_receipt_path"])
    monkeypatch.setattr(controller, "_request", lambda: transaction_request)
    monkeypatch.setattr(
        controller,
        "_execute_validated",
        lambda *args, **kwargs: (_ for _ in ()).throw(interruption),
    )

    assert controller.main() == expected_status
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "reason": "ssh-baseline-transaction-failed",
    }
    assert json.loads(path.read_bytes()) == {
        "schema_version": 1,
        "status": "failed",
        "reason": "controller-failure",
    }
