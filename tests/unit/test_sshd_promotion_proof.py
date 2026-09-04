"""Exact-node promotion proof contract tests; no real SSH or VPN traffic."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/sshd-promotion-proof.py"
PROFILES = ["p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"]


def _identity() -> dict:
    return {
        "inventory_alias": "vpn-p2-fixture",
        "public_service_address_sha256": "a" * 64,
        "deployable_digest": "b" * 64,
        "applied_at": 1_800_000_000,
        "required_profiles": sorted(PROFILES),
        "source_revision": "c" * 40,
        "runner_sha256": "d" * 64,
        "public_profile_digest": "e" * 64,
    }


def _evaluation(identity: dict | None = None) -> dict:
    identity = _identity() if identity is None else identity
    observations = {
        profile: {
            "payload_transport": "tcp-https",
            "target_address_family": "ipv4" if profile == "p2-amneziawg" else "unknown",
            "dns_through_tunnel": True,
            "authenticated_handshake": True,
            **({"fresh_handshake": True} if profile == "p2-amneziawg" else {}),
        }
        for profile in PROFILES
    }
    return {
        "schema_version": 2,
        "evaluated_at": 1_800_000_010,
        "decision": "healthy",
        "candidate_policies": [],
        "failed_vantages": {"fullstack": 0},
        "monitoring_errors": [],
        "evidence": [
            {
                "sentinel": "tls-freeze-a",
                "policy": "fullstack",
                "control": "ok",
                "profiles": dict.fromkeys(PROFILES, "ok"),
                "observed_at": 1_800_000_005,
                "runtime": {},
                "provenance": {
                    "controller_revision": identity["source_revision"],
                    "runner_sha256": identity["runner_sha256"],
                    "client_generation_id": "7f574d16-931e-42b4-a940-853b92f53a14",
                    "public_profile_digest": identity["public_profile_digest"],
                    "vantage": "external",
                },
                "target_identity": identity,
                "profile_observations": observations,
            }
        ],
    }


def _private_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def _load():
    spec = importlib.util.spec_from_file_location("sshd_promotion_proof", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config(tmp_path: Path) -> Path:
    liveness = tmp_path / "liveness.yaml"
    identity = _identity()
    liveness.write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "probe_url": "https://probe.example/",
                "expected_status": 204,
                "stale_after_seconds": 120,
                "expected_runtime": {
                    "sing_box": "1.14.0",
                    "xray": "26.3.27",
                    "awg": "1.0.0",
                    "awg_toolchain": "f" * 64,
                },
                "policies": [
                    {
                        "id": "fullstack",
                        "required_profiles": sorted(PROFILES),
                        "min_failed_vantages": 1,
                    }
                ],
                "sentinels": [
                    {
                        "id": "tls-freeze-a",
                        "ssh_target": "sentinel@example",
                        "policy": "fullstack",
                        "vantage": "external",
                        "target": {key: identity[key] for key in (
                            "inventory_alias", "public_service_address_sha256", "deployable_digest", "applied_at"
                        )},
                        "awg_target": {"provider": "vultr", "environment": "p2-vultr", "instance": "vpn_awg"},
                    }
                ],
            },
            sort_keys=True,
        )
    )
    liveness.chmod(0o600)
    config = tmp_path / "promotion.json"
    _private_json(
        config,
        {
            "schema_version": 1,
            "liveness_config": str(liveness),
            "expected_sentinels": ["tls-freeze-a"],
            "target_identity": _identity(),
        },
    )
    return config


def test_validate_config_mode_checks_full_schema_without_evaluation_or_writes(tmp_path):
    config = _config(tmp_path)
    before = {path.name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in tmp_path.iterdir()}

    result = subprocess.run(
        ["python3", "-B", str(SCRIPT), "--validate-config", "--config", str(config)],
        text=True,
        capture_output=True,
        check=False,
    )

    after = {path.name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in tmp_path.iterdir()}
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert after == before


def test_validate_config_mode_refuses_semantically_invalid_liveness_categorically(tmp_path):
    config = _config(tmp_path)
    liveness = Path(json.loads(config.read_text())["liveness_config"])
    document = yaml.safe_load(liveness.read_text())
    document["sentinels"][0]["target"]["deployable_digest"] = "DO_NOT_LEAK_INVALID_DIGEST"
    liveness.write_text(yaml.safe_dump(document, sort_keys=True))

    result = subprocess.run(
        ["python3", "-B", str(SCRIPT), "--validate-config", "--config", str(config)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "sshd-promotion-proof: configuration-refused\n"
    assert "DO_NOT_LEAK" not in result.stderr


def test_validate_config_mode_refuses_valid_but_wrong_exact_node_binding(tmp_path):
    config = _config(tmp_path)
    liveness = Path(json.loads(config.read_text())["liveness_config"])
    document = yaml.safe_load(liveness.read_text())
    document["sentinels"][0]["target"]["deployable_digest"] = "f" * 64
    liveness.write_text(yaml.safe_dump(document, sort_keys=True))

    result = subprocess.run(
        ["python3", "-B", str(SCRIPT), "--validate-config", "--config", str(config)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "sshd-promotion-proof: configuration-refused\n"


def test_exact_node_all_ok_evaluation_returns_only_safe_controller_identity(tmp_path, monkeypatch):
    module = _load()
    config = _config(tmp_path)
    monkeypatch.setattr(module, "evaluate", lambda _path: _evaluation())

    receipt = module.prove(config)

    assert receipt["status"] == "passed"
    assert set(receipt) == {"schema_version", "status", "target_identity", "observed_at"}
    assert receipt["target_identity"] == {
        "inventory_alias": "vpn-p2-fixture",
        "public_service_address_sha256": "a" * 64,
        "deployable_digest": "b" * 64,
    }
    serialized = json.dumps(receipt)
    assert _identity()["source_revision"] not in serialized
    assert _identity()["runner_sha256"] not in serialized
    assert _identity()["public_profile_digest"] not in serialized


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "degraded",
        "throttled",
        "wrong-target",
        "wrong-source",
        "missing-profile",
        "extra-profile",
        "stale-before-apply",
        "stale",
        "missing-dns",
        "missing-auth",
        "missing-awg-handshake",
    ],
)
def test_non_exact_or_non_positive_evidence_is_refused_categorically(tmp_path, monkeypatch, mutation):
    module = _load()
    config = _config(tmp_path)
    payload = _evaluation()
    evidence = payload["evidence"][0]
    if mutation in {"unknown", "degraded"}:
        payload["decision"] = mutation
    elif mutation == "throttled":
        evidence["profiles"]["p0-reality"] = "throttled"
    elif mutation == "wrong-target":
        evidence["target_identity"] = {**_identity(), "deployable_digest": "f" * 64}
    elif mutation == "wrong-source":
        evidence["provenance"]["controller_revision"] = "f" * 40
    elif mutation == "missing-profile":
        del evidence["profiles"]["p1-xhttp"]
    elif mutation == "extra-profile":
        evidence["profiles"]["p9-extra"] = "ok"
    elif mutation == "stale-before-apply":
        evidence["observed_at"] = _identity()["applied_at"] - 1
    elif mutation == "stale":
        payload["evaluated_at"] = evidence["observed_at"] + 121
    elif mutation == "missing-dns":
        evidence["profile_observations"]["p0-reality"]["dns_through_tunnel"] = False
    elif mutation == "missing-auth":
        evidence["profile_observations"]["p0-reality"]["authenticated_handshake"] = False
    else:
        evidence["profile_observations"]["p2-amneziawg"]["fresh_handshake"] = False
    monkeypatch.setattr(module, "evaluate", lambda _path: payload)

    with pytest.raises(module.ProofError) as error:
        module.prove(config)

    assert str(error.value) == "proof-refused"


def test_config_and_liveness_paths_are_owner_private_regular_files(tmp_path, monkeypatch):
    module = _load()
    config = _config(tmp_path)
    monkeypatch.setattr(module, "evaluate", lambda _path: _evaluation())
    config.chmod(0o644)
    with pytest.raises(module.ProofError, match="configuration-refused"):
        module.prove(config)
    config.chmod(0o600)
    liveness = Path(json.loads(config.read_text())["liveness_config"])
    liveness.chmod(0o644)
    with pytest.raises(module.ProofError, match="configuration-refused"):
        module.prove(config)
    liveness.chmod(0o600)
    replacement = tmp_path / "replacement.yaml"
    replacement.write_text("schema_version: 2\n")
    replacement.chmod(0o600)
    liveness.unlink()
    liveness.symlink_to(replacement)
    with pytest.raises(module.ProofError, match="configuration-refused"):
        module.prove(config)


def test_duplicate_config_keys_are_refused_before_evaluation(tmp_path, monkeypatch):
    module = _load()
    config = _config(tmp_path)
    raw = config.read_text()
    config.write_text(raw[:-1] + ',"schema_version":1}')
    monkeypatch.setattr(module, "evaluate", lambda _path: pytest.fail("must not evaluate"))

    with pytest.raises(module.ProofError, match="configuration-refused"):
        module.prove(config)


def test_fixed_evaluator_gets_only_controlled_executor_environment(tmp_path, monkeypatch):
    module = _load()
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text(
        "import json,os\n"
        "print(json.dumps({'environment': dict(os.environ)}))\n"
    )
    monkeypatch.setattr(module, "EVALUATOR", evaluator)
    monkeypatch.setenv("PATH", str(tmp_path / "untrusted-bin"))
    monkeypatch.setenv("SSH_AUTH_SOCK", "DO_NOT_FORWARD_AGENT")

    result = module.evaluate(b"schema_version: 2\n")

    environment = result["environment"]
    assert environment["PATH"] == module.EXECUTOR_PATH
    assert environment["LANG"] == environment["LC_ALL"] == "C"
    assert "SSH_AUTH_SOCK" not in environment
    # macOS may inject its own locale encoding marker into every child.
    assert set(environment) - {"__CF_USER_TEXT_ENCODING"} <= {"PATH", "HOME", "LANG", "LC_ALL"}


def test_promotion_freshness_is_capped_and_spawn_failure_is_categorical(tmp_path, monkeypatch):
    module = _load()
    config = _config(tmp_path)
    liveness = Path(json.loads(config.read_text())["liveness_config"])
    document = yaml.safe_load(liveness.read_text())
    document["stale_after_seconds"] = 3600
    liveness.write_text(yaml.safe_dump(document, sort_keys=True))
    loaded, _ = module.load_config(config)
    assert loaded["_stale_after_seconds"] == module.PROOF_MAX_STALE_SECONDS
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        OSError("DO_NOT_LEAK_MISSING_EVALUATOR")
    ))

    with pytest.raises(module.ProofError) as error:
        module.prove(config)

    assert str(error.value) == "proof-refused"
    assert "DO_NOT_LEAK" not in str(error.value)


def test_cli_errors_are_categorical_and_never_echo_private_values(tmp_path):
    config = _config(tmp_path)
    raw = json.loads(config.read_text())
    raw["target_identity"]["deployable_digest"] = "DO_NOT_LEAK_ADDRESS_OR_SECRET"
    _private_json(config, raw)

    result = subprocess.run(
        ["python3", str(SCRIPT), "--config", str(config)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "sshd-promotion-proof: configuration-refused\n"
    assert "DO_NOT_LEAK" not in result.stderr


def test_disposable_executor_inputs_are_private_and_forwarded_as_exact_snapshots(tmp_path, monkeypatch):
    module = _load()
    config = _config(tmp_path)
    paths = {name: tmp_path / (name + '.json') for name in ('manifest', 'binding')}
    for name, path in paths.items():
        _private_json(path, {'fixture': name})
    document = json.loads(config.read_text())
    document['executor'] = {name: str(path) for name, path in paths.items()}
    _private_json(config, document)
    loaded, liveness = module.load_config(config)
    evaluator = tmp_path / 'capture.py'
    evaluator.write_text(
        'import json,sys,os,pathlib,shutil\n'
        'args=sys.argv[1:]\n'
        'print(json.dumps({"manifest":pathlib.Path(args[args.index("--executor-manifest")+1]).read_text(),'
        '"binding":pathlib.Path(args[args.index("--executor-binding")+1]).read_text(),'
        '"path":os.environ["PATH"],"colima":shutil.which("colima")}))\n'
    )
    monkeypatch.setattr(module, 'EVALUATOR', evaluator)
    # The caller path may change after load; evaluation uses only its snapshots.
    paths['binding'].write_text('FOREIGN_REPLACEMENT')
    monkeypatch.setenv('PATH', str(tmp_path / 'untrusted'))
    result = module.evaluate(liveness, executor=loaded['_executor_files'])
    assert json.loads(result['manifest']) == {'fixture': 'manifest'}
    assert json.loads(result['binding']) == {'fixture': 'binding'}
    assert result['path'] == module.EXECUTOR_PATH
    assert '/opt/homebrew/bin' in result['path'].split(':')
    assert str(tmp_path / 'untrusted') not in result['path']
    assert result['colima'] == __import__('shutil').which('colima', path=module.EXECUTOR_PATH)


@pytest.mark.parametrize('failure', ['unpaired', 'mode', 'symlink'])
def test_disposable_executor_input_refusal_precedes_evaluation(tmp_path, failure):
    module = _load()
    config = _config(tmp_path)
    manifest, binding = tmp_path / 'manifest.json', tmp_path / 'binding.json'
    _private_json(manifest, {'fixture': 'manifest'})
    _private_json(binding, {'fixture': 'binding'})
    pair = {'manifest': str(manifest), 'binding': str(binding)}
    if failure == 'unpaired':
        del pair['binding']
    elif failure == 'mode':
        binding.chmod(0o644)
    else:
        binding.unlink()
        binding.symlink_to(manifest)
    document = json.loads(config.read_text())
    document['executor'] = pair
    _private_json(config, document)
    with pytest.raises(module.ProofError, match='configuration-refused'):
        module.load_config(config)
