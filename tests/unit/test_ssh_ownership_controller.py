"""The explicit ownership step preserves dual-path proof and rollback ordering."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def configured(tmp_path, monkeypatch):
    operator = load("ssh-ownership")
    deploy = load("deploy-controller")
    controller = load("sshd-baseline-controller")
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
    known.write_text("[192.0.2.10]:2222 ssh-ed25519 fixture-pin\n")
    contexts = tmp_path / "contexts.json"
    contexts.write_text(json.dumps({"node-a": [
        {"user": "deploy", "host": "controller-a", "addr": "198.51.100.2",
         "laddr": "192.0.2.10", "lport": 2222},
        {"user": "deploy", "host": "controller-a", "addr": "100.64.0.2",
         "laddr": "100.64.0.10", "lport": 2222},
    ]}))
    contexts.chmod(0o600)
    config = tmp_path / "ownership.json"
    data = {"schema_version": 1, "mode": "check", "inventory_alias": "node-a",
            "inventory_path": str(inventory), "known_hosts_path": str(known),
            "contexts_path": str(contexts), "source_revision": "a" * 40,
            "deployable_digest": "b" * 64}
    config.write_text(json.dumps(data))
    config.chmod(0o600)
    monkeypatch.setattr(deploy, "source_identity", lambda *args, **kwargs: {
        "DEPLOY_SOURCE_REVISION": "a" * 40, "DEPLOYABLE_SOURCE_DIGEST": "b" * 64})
    monkeypatch.setattr(operator, "_module", lambda name: deploy if name == "deploy-controller" else controller)
    monkeypatch.setattr(operator, "bundle_manifest", lambda: ("c" * 64, ""))
    return operator, controller, config, data, contexts


def test_check_previews_only_ownership_without_candidate_or_activation(configured, monkeypatch):
    operator, controller, config, _, _ = configured
    calls = []

    def rpc(host, pin, action, request, environment, **kwargs):
        calls.append((action, request))
        return {"status": "would-change", "snapshot_digest": "d" * 64}

    monkeypatch.setattr(controller, "transaction_rpc", rpc)
    assert operator.execute(config) == {"status": "would-change"}
    assert len(calls) == 1
    assert calls[0][0] == "prepare"
    assert calls[0][1]["intent"] == "sshd-ownership"
    assert calls[0][1]["check_mode"] is True
    assert "hardening_b64" not in calls[0][1]


def test_deploy_checks_both_transports_before_confirm(configured, monkeypatch):
    operator, controller, config, data, _ = configured
    data["mode"] = "deploy"
    config.write_text(json.dumps(data))
    calls = []
    receipt = {"generation": "00000000-0000-4000-8000-000000000001",
               "nonce": "d" * 64, "deadline": 999, "snapshot_digest": "e" * 64}

    def rpc(host, pin, action, request, environment, **kwargs):
        calls.append((action, host["transport"]))
        status = {"prepare": "prepared", "apply": "applied", "confirm": "committed",
                  "status": "committed" if ("confirm", "100.64.0.10") in calls else "applied"}[action]
        return receipt | {"status": status}

    monkeypatch.setattr(controller, "transaction_rpc", rpc)
    monkeypatch.setattr(controller, "fresh_sftp", lambda host, pin, env: calls.append(("sftp", host["transport"])))
    assert operator.execute(config) == {"status": "committed"}
    assert calls == [
        ("prepare", "100.64.0.10"), ("apply", "100.64.0.10"),
        ("status", "192.0.2.10"), ("sftp", "192.0.2.10"),
        ("status", "100.64.0.10"), ("sftp", "100.64.0.10"),
        ("status", "100.64.0.10"), ("confirm", "100.64.0.10"),
        ("status", "100.64.0.10"),
    ]


def test_failed_management_sftp_rolls_back(configured, monkeypatch):
    operator, controller, config, data, _ = configured
    data["mode"] = "deploy"
    config.write_text(json.dumps(data))
    calls = []
    receipt = {"generation": "00000000-0000-4000-8000-000000000001",
               "nonce": "d" * 64, "deadline": 999, "snapshot_digest": "e" * 64}

    def rpc(host, pin, action, request, environment, **kwargs):
        calls.append(action)
        return receipt | {"status": {"prepare": "prepared", "apply": "applied",
                                    "status": "applied", "rollback": "rolled_back"}[action]}

    def sftp(host, pin, env):
        if host["transport"] == "100.64.0.10":
            raise controller.BaselineError("fresh-sftp-failed")

    monkeypatch.setattr(controller, "transaction_rpc", rpc)
    monkeypatch.setattr(controller, "fresh_sftp", sftp)
    with pytest.raises(controller.BaselineError, match="fresh-sftp-failed"):
        operator.execute(config)
    assert calls[-1] == "rollback"
    assert "confirm" not in calls


def test_unrelated_context_or_source_refuses_before_rpc(configured, monkeypatch):
    operator, controller, config, data, contexts = configured
    calls = []
    monkeypatch.setattr(controller, "transaction_rpc", lambda *args, **kwargs: calls.append(args))
    data["source_revision"] = "f" * 40
    config.write_text(json.dumps(data))
    with pytest.raises(operator.OwnershipControllerError, match="source-changed"):
        operator.execute(config)
    data["source_revision"] = "a" * 40
    config.write_text(json.dumps(data))
    contexts.write_text(json.dumps({"another-node": []}))
    with pytest.raises(operator.OwnershipControllerError, match="contexts-invalid"):
        operator.execute(config)
    assert calls == []


def test_mutation_requires_clean_exact_source(configured, monkeypatch):
    operator, controller, config, data, _ = configured
    data["mode"] = "deploy"
    config.write_text(json.dumps(data))
    deploy = operator._module("deploy-controller")
    def source(root, environment, *, require_clean):
        assert require_clean is True
        raise deploy.DeployError("clean source required")
    monkeypatch.setattr(deploy, "source_identity", source)
    monkeypatch.setattr(controller, "transaction_rpc", lambda *args, **kwargs: pytest.fail("RPC before source check"))
    with pytest.raises(deploy.DeployError, match="clean source required"):
        operator.execute(config)
