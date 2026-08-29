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
    proof.write_text("fixture")
    proof.chmod(0o600)
    return {
        "schema_version": 1, "mode": "deploy", "inventory_alias": "node-a",
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
    transaction_request = dict(transaction_request, mode="check", promotion_config_path=None)
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
