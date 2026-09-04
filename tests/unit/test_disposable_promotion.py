"""First-onboarding controller contracts; fixture execution is not live proof."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def intent(tmp_path):
    fixture = load(
        "promotion_fixture", ROOT / "tests/unit/test_sshd_promotion_proof.py"
    )
    promotion = json.loads(fixture._config(tmp_path).read_text())
    config = yaml.safe_load(Path(promotion["liveness_config"]).read_bytes())
    target = {
        key: promotion["target_identity"][key]
        for key in (
            "inventory_alias",
            "public_service_address_sha256",
            "deployable_digest",
        )
    }
    config["sentinels"][0]["target"] = target
    config["sentinels"][0]["awg_target"] = {
        "provider": "upcloud",
        "environment": "ci-staging-fixture",
        "instance": "vpn_awg",
    }
    return {
        "schema_version": 1,
        "kind": "disposable-staging-intent",
        "target_identity": target,
        "host": "upcloud:ci-staging-fixture",
        "cohort": "device-full-staging",
        "client": "staging-client",
        "liveness": config,
        "inputs": {
            key: str(tmp_path / key)
            for key in (
                "sops_file",
                "age_key_file",
                "awg_key_file",
                "executor_manifest",
                "cleanup_manifest",
            )
        },
        "outputs": {
            key: str(tmp_path / ("output-" + key))
            for key in (
                "liveness_config",
                "registry",
                "binding",
                "promotion_config",
                "authority",
                "executor_manifest",
            )
        },
    }


def module():
    return load("disposable_promotion", ROOT / "scripts/disposable_promotion.py")


def test_intent_validation_needs_no_files_or_fake_binding_epoch(intent):
    original = copy.deepcopy(intent)
    assert module().validate_intent(intent) == original
    assert intent == original
    assert "applied_at" not in intent["liveness"]["sentinels"][0]["target"]
    assert all(not Path(path).exists() for path in intent["inputs"].values())


@pytest.mark.parametrize(
    "case",
    [
        "prod",
        "foreign-provider",
        "wrong-cohort",
        "missing-profile",
        "extra-sentinel",
        "foreign-target",
        "foreign-awg",
        "epoch",
        "missing-runtime",
        "relative-input",
        "aliased-output",
        "parent-traversal",
        "extra-field",
        "bool-schema",
        "missing-client",
        "unknown-policy",
        "quorum",
        "missing-age",
        "output-over-input",
    ],
)
def test_intent_refuses_ambiguous_or_broader_authority_without_io(intent, case):
    if case == "prod":
        intent["host"] = "upcloud:prod"
    elif case == "foreign-provider":
        intent["host"] = "vultr:ci-staging-fixture"
    elif case == "wrong-cohort":
        intent["cohort"] = "fullstack"
    elif case == "missing-profile":
        intent["liveness"]["policies"][0]["required_profiles"].pop()
    elif case == "extra-sentinel":
        intent["liveness"]["sentinels"].append(
            copy.deepcopy(intent["liveness"]["sentinels"][0])
        )
    elif case == "foreign-target":
        intent["target_identity"] = dict(
            intent["target_identity"], deployable_digest="c" * 64
        )
    elif case == "foreign-awg":
        intent["liveness"]["sentinels"][0]["awg_target"][
            "environment"
        ] = "ci-staging-other"
    elif case == "epoch":
        intent["liveness"]["sentinels"][0]["target"]["applied_at"] = 1
    elif case == "missing-runtime":
        del intent["liveness"]["expected_runtime"]["awg_toolchain"]
    elif case == "relative-input":
        intent["inputs"]["awg_key_file"] = "relative-key"
    elif case == "aliased-output":
        intent["outputs"]["binding"] = intent["outputs"]["registry"]
    elif case == "parent-traversal":
        intent["outputs"]["binding"] += "/../replacement"
    elif case == "extra-field":
        intent["command"] = "/bin/true"
    elif case == "bool-schema":
        intent["schema_version"] = True
    elif case == "missing-client":
        intent["client"] = ""
    elif case == "unknown-policy":
        intent["liveness"]["sentinels"][0]["policy"] = "other"
    elif case == "quorum":
        intent["liveness"]["policies"][0]["min_failed_vantages"] = 2
    elif case == "missing-age":
        del intent["inputs"]["age_key_file"]
    elif case == "output-over-input":
        intent["outputs"]["binding"] = intent["inputs"]["awg_key_file"]
    helper = module()
    with pytest.raises(helper.OnboardingError, match="^onboarding-intent-refused$"):
        helper.validate_intent(intent)


@pytest.fixture
def capabilities(intent, tmp_path):
    from datetime import datetime, timezone
    import hashlib

    fixture = load("cleanup_fixture", ROOT / "tests/unit/test_staging_cleanup_guard.py")
    guard = fixture.guard
    private = tmp_path.resolve() / "capabilities"
    private.mkdir(mode=0o700)
    state = fixture._state_view()
    state["outputs"] = {"server_ipv4": {"value": "192.0.2.10"}}
    state_path = private / "state.json"
    fixture._private_file(state_path, guard.canonical_json(state))
    cleanup = private / "cleanup.json"
    guard.create_manifest(
        output_path=cleanup,
        provider="upcloud",
        environment="ci-staging-fixture",
        workspace="ci-staging-fixture",
        state_path=state_path,
        hostname=fixture.HOSTNAME,
        request_json=fixture._fresh_creation_get,
        now=datetime.now(timezone.utc),
    )
    intent["target_identity"]["inventory_alias"] = fixture.HOSTNAME
    intent["target_identity"]["public_service_address_sha256"] = hashlib.sha256(
        b"192.0.2.10"
    ).hexdigest()
    secrets = {
        "client_registry": {
            "staging-client": {"status": "issued", "awg_private_key": "A" * 43 + "="}
        }
    }
    for name in intent["inputs"]:
        path = private / name
        raw = (
            ("A" * 43 + "=\n").encode()
            if name == "awg_key_file"
            else b"fixture-private-input"
        )
        if name == "executor_manifest":
            executor_id = "00000000-0000-4000-8000-000000000009"
            raw = guard.canonical_json(
                {
                    "schema_version": 1,
                    "kind": "colima-systemd",
                    "profile": "vpn-liveness-fixture",
                    "executor_id": executor_id,
                    "created_at": int(datetime.now(timezone.utc).timestamp()),
                    "expires_at": int(datetime.now(timezone.utc).timestamp()) + 3600,
                    "initial_docker_context": "fixture",
                    "profile_config_sha256": "a" * 64,
                    "profile_status_sha256": "b" * 64,
                    "mount_table_sha256": "c" * 64,
                    "executor_marker_sha256": hashlib.sha256(
                        (executor_id + "\n").encode()
                    ).hexdigest(),
                }
            )
        fixture._private_file(path, raw)
        intent["inputs"][name] = str(path)
    intent["inputs"]["cleanup_manifest"] = str(cleanup)
    for name in intent["outputs"]:
        intent["outputs"][name] = str(private / (name + ".json"))
    controller_dir = tmp_path.resolve() / "controller"
    controller_dir.mkdir(mode=0o700)
    return {
        "intent": intent,
        "host": {
            "name": intent["target_identity"]["inventory_alias"],
            "address": "192.0.2.10",
        },
        "memberships": ["vpn-device-full-staging"],
        "directory": controller_dir,
        "deployed_secrets": yaml.safe_dump(secrets).encode(),
        "environment": {},
    }


def test_capabilities_bind_state_and_snapshot_exact_secrets_before_deployment(
    capabilities, monkeypatch
):
    helper = module()
    original = copy.deepcopy(capabilities["intent"])
    calls = []

    def decrypt(sops, age, output, environment):
        calls.append((sops, age))
        assert sops.read_bytes() == Path(original["inputs"]["sops_file"]).read_bytes()
        output.write_bytes(capabilities["deployed_secrets"])
        output.chmod(0o600)

    monkeypatch.setattr(helper, "_decrypt", decrypt)
    prepared = helper.prepare_intent(**capabilities)
    assert len(calls) == 1
    for name, source in original["inputs"].items():
        snapshot = Path(prepared["inputs"][name])
        assert snapshot != Path(source)
        assert snapshot.read_bytes() == Path(source).read_bytes()
        assert snapshot.stat().st_mode & 0o777 == 0o600
    assert prepared["outputs"] == original["outputs"]
    assert not (capabilities["directory"] / "onboarding-secrets.yaml").exists()


def test_capability_snapshot_decrypts_with_real_sops_yaml(capabilities, tmp_path):
    import os

    roundtrip = load("sops_roundtrip", ROOT / "tests/unit/test_sops_roundtrip.py")
    roundtrip._require_binaries()
    plain = tmp_path / "fixture.yaml"
    plain.write_bytes(capabilities["deployed_secrets"])
    plain.chmod(0o600)
    encrypted = tmp_path / "fixture.sops.yaml"
    roundtrip._sops_encrypt(
        plain,
        encrypted,
        roundtrip.AGE_KEY,
        roundtrip._age_recipient(roundtrip.AGE_KEY),
    )
    inputs = capabilities["intent"]["inputs"]
    Path(inputs["sops_file"]).write_bytes(encrypted.read_bytes())
    Path(inputs["age_key_file"]).write_bytes(roundtrip.AGE_KEY.read_bytes())
    capabilities["environment"] = {
        key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ
    }

    prepared = module().prepare_intent(**capabilities)

    assert Path(prepared["inputs"]["sops_file"]).read_bytes() == encrypted.read_bytes()
    assert prepared["outputs"] == capabilities["intent"]["outputs"]
    assert not (capabilities["directory"] / "onboarding-secrets.yaml").exists()
    assert all(not Path(path).exists() for path in prepared["outputs"].values())


@pytest.mark.parametrize(
    "case",
    [
        "address",
        "alias",
        "cohort",
        "sops-mismatch",
        "key-mismatch",
        "revoked",
        "unsafe-key",
        "symlink-key",
        "ephemeral-output",
    ],
)
def test_capability_refusal_never_becomes_host_action(capabilities, monkeypatch, case):
    helper = module()
    if case == "address":
        capabilities["host"]["address"] = "192.0.2.99"
    elif case == "alias":
        capabilities["host"]["name"] = "foreign-node"
    elif case == "cohort":
        capabilities["memberships"] = ["vpn-fullstack"]
    elif case == "key-mismatch":
        Path(capabilities["intent"]["inputs"]["awg_key_file"]).write_text(
            "B" * 43 + "=\n"
        )
    elif case == "unsafe-key":
        Path(capabilities["intent"]["inputs"]["awg_key_file"]).chmod(0o644)
    elif case == "symlink-key":
        key = Path(capabilities["intent"]["inputs"]["awg_key_file"])
        other = key.with_suffix(".other")
        key.rename(other)
        key.symlink_to(other)
    elif case == "ephemeral-output":
        capabilities["intent"]["outputs"]["binding"] = str(
            capabilities["directory"] / "lost-binding"
        )

    def decrypt(sops, age, output, environment):
        doc = yaml.safe_load(capabilities["deployed_secrets"])
        if case == "sops-mismatch":
            doc["foreign"] = True
        if case == "revoked":
            doc["client_registry"]["staging-client"]["status"] = "revoked"
            capabilities["deployed_secrets"] = yaml.safe_dump(doc).encode()
        output.write_text(yaml.safe_dump(doc))
        output.chmod(0o600)

    monkeypatch.setattr(helper, "_decrypt", decrypt)
    with pytest.raises(helper.OnboardingError, match="^onboarding-capability-refused$"):
        helper.prepare_intent(**capabilities)
    assert not (capabilities["directory"] / "onboarding-secrets.yaml").exists()
    assert all(
        not Path(path).exists() for path in capabilities["intent"]["outputs"].values()
    )


@pytest.fixture
def finalization(capabilities, monkeypatch):
    import hashlib
    import install_liveness_sentinel as installer
    import disposable_liveness_executor as executor

    helper = module()
    state = {"installs": 0, "reads": 0, "live": 0, "receipt": None}
    intent = capabilities["intent"]
    config_path = Path(intent["outputs"]["liveness_config"])
    binding_path = Path(intent["outputs"]["binding"])
    registry_path = Path(intent["outputs"]["registry"])
    source = ("c" * 40, b"runner", b"engine")
    monkeypatch.setattr(installer, "_source_identity", lambda _root: source)

    def install(config, sid, client, registry, **kwargs):
        state["installs"] += 1
        assert config == config_path and registry == registry_path
        assert kwargs["stdin"].read() == "A" * 43 + "=\n"
        assert kwargs["environment"]["HOSTS"] == intent["host"]
        assert kwargs["environment"]["COHORTS"] == "device-full-staging"
        assert kwargs["read_awg_stdin"] is True
        target = json.loads(config.read_bytes())["sentinels"][0]["target"]
        provenance = {
            "controller_revision": source[0],
            "runner_sha256": hashlib.sha256(source[1]).hexdigest(),
            "client_generation_id": "00000000-0000-4000-8000-000000000001",
            "public_profile_digest": "e" * 64,
            "vantage": "external",
        }
        target.update(
            required_profiles=sorted(helper.PROFILES),
            source_revision=source[0],
            runner_sha256=provenance["runner_sha256"],
            public_profile_digest="e" * 64,
        )
        sentinel = intent["liveness"]["sentinels"][0]
        binding = {
            "profile": "vpn-liveness-fixture",
            "target_identity": target,
            "provenance": provenance,
            "generation_id": provenance["client_generation_id"],
            "sentinel": sid,
            "client": client,
            "cleanup_manifest_sha256": hashlib.sha256(
                Path(intent["inputs"]["cleanup_manifest"]).read_bytes()
            ).hexdigest(),
        }
        executor._write_new(binding_path, binding)
        entry = {
            "client": client,
            "ssh_target": sentinel["ssh_target"],
            "policy": sentinel["policy"],
            "vantage": sentinel["vantage"],
            "generation_id": provenance["client_generation_id"],
            "provenance": provenance,
            "required_profiles": sorted(helper.PROFILES),
            "target_identity": target,
            "executor_binding_sha256": executor.binding_digest(binding_path),
        }
        executor._write_new(
            registry_path, {"schema_version": 2, "sentinels": {sid: entry}}
        )
        state["receipt"] = {
            "generation_id": provenance["client_generation_id"],
            "status": "committed",
            "runner_sha256": provenance["runner_sha256"],
            "provenance": provenance,
            "target_identity": target,
        }
        return state["receipt"]

    def bound(*args, **kwargs):
        state["live"] += 1
        return executor._read_private(binding_path)[0]

    def receipt(*args, **kwargs):
        state["reads"] += 1
        return state["receipt"]

    monkeypatch.setattr(installer, "install", install)
    monkeypatch.setattr(installer, "_receipt", receipt)
    monkeypatch.setattr(executor, "load_bound_executor", bound)
    return helper, intent, state


def test_finalizer_publishes_real_epoch_and_reuses_exact_receipt_without_reinstall(
    finalization,
):
    helper, intent, state = finalization
    result = helper.finalize(intent, {}, clock=lambda: 1_800_000_000)
    assert result == Path(intent["outputs"]["promotion_config"])
    config = json.loads(result.read_bytes())
    assert config["target_identity"]["applied_at"] == 1_800_000_000
    assert config["executor"] == {
        "manifest": intent["outputs"]["executor_manifest"],
        "binding": intent["outputs"]["binding"],
    }
    before = {path: Path(path).read_bytes() for path in intent["outputs"].values()}
    assert helper.finalize(intent, {}, clock=lambda: 1_800_000_100) == result
    assert state["installs"] == 1
    assert state["reads"] == 1
    assert before == {
        path: Path(path).read_bytes() for path in intent["outputs"].values()
    }


@pytest.mark.parametrize(
    "case",
    [
        "foreign-output",
        "changed-sops",
        "foreign-receipt",
        "no-remote-receipt",
        "changed-target",
    ],
)
def test_finalizer_reuse_never_overwrites_foreign_or_unproven_generation(
    finalization, case
):
    helper, intent, state = finalization
    helper.finalize(intent, {}, clock=lambda: 1_800_000_000)
    if case == "foreign-output":
        Path(intent["outputs"]["promotion_config"]).write_text('{"foreign":true}')
    elif case == "changed-sops":
        Path(intent["inputs"]["sops_file"]).write_text("different ciphertext")
    elif case == "foreign-receipt":
        state["receipt"] = dict(
            state["receipt"], generation_id="00000000-0000-4000-8000-000000000002"
        )
    elif case == "no-remote-receipt":
        state["receipt"] = None
    elif case == "changed-target":
        intent["target_identity"]["deployable_digest"] = "f" * 64
    before = {path: Path(path).read_bytes() for path in intent["outputs"].values()}
    with pytest.raises(
        helper.OnboardingError, match="^onboarding-finalization-refused$"
    ):
        helper.finalize(intent, {}, clock=lambda: 1_800_000_100)
    assert state["installs"] == 1
    assert before == {
        path: Path(path).read_bytes() for path in intent["outputs"].values()
    }


def test_deploy_controller_prepares_intent_before_any_checked_command(
    capabilities, monkeypatch
):
    helper = module()
    monkeypatch.setitem(sys.modules, "disposable_promotion", helper)
    controller = load("onboarding_deploy", ROOT / "scripts/deploy-controller.py")
    host = dict(capabilities["host"], transport="100.64.0.10", port=22)
    directory = capabilities["directory"]
    contexts = [
        {
            "user": "deploy",
            "host": "mac",
            "addr": source,
            "laddr": destination,
            "lport": 22,
        }
        for source, destination in (
            ("198.51.100.1", host["address"]),
            ("100.64.0.1", host["transport"]),
        )
    ]
    for variable, name, doc in (
        ("DEPLOY_SSH_CONTEXTS_FILE", "contexts.json", {host["name"]: contexts}),
        (
            "DEPLOY_PROMOTION_CONFIG_FILE",
            "promotions.json",
            {host["name"]: capabilities["intent"]},
        ),
    ):
        path = directory / name
        path.write_text(json.dumps(doc))
        path.chmod(0o600)
        monkeypatch.setenv(variable, str(path))
    monkeypatch.setattr(controller, "bundle_manifest", lambda: ("b" * 64, {}))
    calls = []

    def decrypt(sops, age, output, environment):
        calls.append("decrypt")
        output.write_bytes(capabilities["deployed_secrets"])
        output.chmod(0o600)

    def checked(command, **kwargs):
        calls.append("validate")
        document = json.loads(Path(command[-1]).read_bytes())
        assert Path(document["inputs"]["awg_key_file"]).parent == directory
        helper.validate_intent(document)

    monkeypatch.setattr(helper, "_decrypt", decrypt)
    monkeypatch.setattr(controller, "checked", checked)
    result = controller.transaction_inputs(
        "deploy",
        [host],
        {
            "DEPLOYABLE_SOURCE_DIGEST": capabilities["intent"]["target_identity"][
                "deployable_digest"
            ]
        },
        directory,
        ROOT,
        {},
        memberships={host["name"]: capabilities["memberships"]},
        deployed_secrets=capabilities["deployed_secrets"],
    )
    assert calls == ["decrypt", "validate"]
    assert result[host["name"]]["ssh_transaction_promotion_config_path"]


def test_promotion_cli_accepts_intent_only_in_validation_mode(intent, tmp_path):
    import subprocess

    path = tmp_path / "intent.json"
    path.write_text(json.dumps(intent))
    path.chmod(0o600)
    command = [
        sys.executable,
        str(ROOT / "scripts/sshd-promotion-proof.py"),
        "--config",
        str(path),
    ]
    valid = subprocess.run(
        command + ["--validate-config"], capture_output=True, timeout=15
    )
    assert valid.returncode == 0, valid.stderr
    prove = subprocess.run(command, capture_output=True, timeout=15)
    assert prove.returncode != 0
    assert prove.stdout == b""
    assert not any(Path(path).exists() for path in intent["inputs"].values())


@pytest.mark.parametrize("boundary", ["epoch", "config", "executor-manifest"])
def test_interrupted_local_publication_reuses_original_epoch(
    finalization, monkeypatch, boundary
):
    import disposable_liveness_executor as executor

    helper, intent, state = finalization
    original = executor._write_new
    stop = {
        "epoch": "authority",
        "config": "liveness_config",
        "executor-manifest": "executor_manifest",
    }[boundary]

    def interrupted(path, value):
        original(path, value)
        if path == Path(intent["outputs"][stop]):
            raise OSError("fixture local publication interruption")

    monkeypatch.setattr(executor, "_write_new", interrupted)
    with pytest.raises(helper.OnboardingError):
        helper.finalize(intent, {}, clock=lambda: 1_800_000_000)
    assert state["installs"] == 0
    monkeypatch.setattr(executor, "_write_new", original)
    output = helper.finalize(intent, {}, clock=lambda: 1_800_000_100)
    assert (
        json.loads(output.read_bytes())["target_identity"]["applied_at"]
        == 1_800_000_000
    )
    assert state["installs"] == 1


def test_completed_reuse_does_not_reopen_key(finalization, monkeypatch):
    helper, intent, state = finalization
    helper.finalize(intent, {}, clock=lambda: 1_800_000_000)
    # The deploy controller already fenced and checked the encrypted client.
    # Retry finalization only needs its persistent receipt and public binding.
    Path(intent["inputs"]["awg_key_file"]).unlink()
    helper.finalize(intent, {}, clock=lambda: 1_800_000_100)
    assert state["installs"] == 1 and state["reads"] == 1


def test_finalizer_rejects_existing_output_without_its_authority(finalization):
    helper, intent, state = finalization
    output = Path(intent["outputs"]["registry"])
    output.write_text('{"foreign":true}')
    output.chmod(0o600)
    before = output.read_bytes(), output.stat().st_ino
    with pytest.raises(helper.OnboardingError):
        helper.finalize(intent, {}, clock=lambda: 1_800_000_000)
    assert (output.read_bytes(), output.stat().st_ino) == before
    assert state["installs"] == 0
    assert not Path(intent["outputs"]["authority"]).exists()


@pytest.mark.parametrize("suffix", [".pending.json", ".lock"])
def test_intent_rejects_derived_registry_paths_aliasing_key(intent, suffix):
    intent["inputs"]["awg_key_file"] = intent["outputs"]["registry"] + suffix
    helper = module()
    with pytest.raises(helper.OnboardingError):
        helper.validate_intent(intent)


@pytest.mark.parametrize("case", ["expired", "invalid", "default-profile"])
def test_invalid_executor_manifest_refuses_before_decrypt(
    capabilities, monkeypatch, case
):
    import time

    helper = module()
    path = Path(capabilities["intent"]["inputs"]["executor_manifest"])
    doc = json.loads(path.read_bytes())
    if case == "expired":
        doc["created_at"] = int(time.time()) - 20
        doc["expires_at"] = int(time.time()) - 1
    elif case == "default-profile":
        doc["profile"] = "default"
    else:
        doc = {}
    path.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")
    calls = []
    monkeypatch.setattr(helper, "_decrypt", lambda *args: calls.append("decrypt"))
    with pytest.raises(helper.OnboardingError):
        helper.prepare_intent(**capabilities)
    assert calls == []


def test_baseline_real_dispatch_finalizes_before_first_rpc(
    finalization, tmp_path, monkeypatch
):
    helper, intent, state = finalization
    monkeypatch.setitem(sys.modules, "disposable_promotion", helper)
    fixtures = load(
        "baseline_fixture", ROOT / "tests/unit/test_sshd_baseline_controller.py"
    )
    request = fixtures.transaction_request.__wrapped__(tmp_path)
    alias = intent["target_identity"]["inventory_alias"]
    inventory = Path(request["inventory_path"])
    inventory.write_text(inventory.read_text().replace("node-a ", alias + " "))
    request["inventory_alias"] = alias
    request["target_identity"] = intent["target_identity"]
    Path(request["promotion_config_path"]).write_text(json.dumps(intent))
    controller = fixtures.module()
    calls = []

    def proof(root, path, environment):
        assert state["installs"] == 1
        assert path == Path(intent["outputs"]["promotion_config"])
        calls.append("fresh-proof")
        return fixtures.proof_receipt(request)

    def rpc(host, known, action, payload, environment):
        assert calls == ["fresh-proof"]
        assert state["installs"] == 1
        assert action == "prepare"
        calls.append("prepare")
        return {"status": "unchanged"}

    assert controller.execute(request, {}, proof=proof, rpc=rpc, clock=lambda: 100) == {
        "status": "unchanged"
    }
    assert calls == ["fresh-proof", "prepare"]


def test_plaintext_cleanup_failure_refuses_without_private_exception_context(
    capabilities, monkeypatch
):
    import traceback

    helper = module()
    plaintext = capabilities["directory"] / "onboarding-secrets.yaml"
    original_unlink = Path.unlink
    continuation = []

    def decrypt(sops, age, output, environment):
        output.write_bytes(capabilities["deployed_secrets"])
        output.chmod(0o600)

    def fail_unlink(path, *args, **kwargs):
        if path == plaintext:
            raise OSError(
                "private fault "
                + str(path)
                + " "
                + capabilities["deployed_secrets"].decode()
            )
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(helper, "_decrypt", decrypt)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(helper.OnboardingError) as caught:
        result = helper.prepare_intent(**capabilities)
        continuation.append(result)
    assert continuation == []
    assert str(caught.value) == "onboarding-cleanup-incomplete"
    assert caught.value.__suppress_context__ is True
    rendered = "".join(traceback.format_exception(caught.value))
    assert str(plaintext) not in rendered
    assert capabilities["deployed_secrets"].decode() not in rendered
    assert plaintext.read_bytes() == capabilities["deployed_secrets"]
    assert plaintext.stat().st_mode & 0o777 == 0o600
    assert all(
        not Path(path).exists() for path in capabilities["intent"]["outputs"].values()
    )
