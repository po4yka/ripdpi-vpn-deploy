"""Real filesystem transaction tests; probe callbacks are not VPN acceptance."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import pytest


ENGINE = Path(__file__).resolve().parents[2] / "scripts/liveness_generation.py"


@pytest.fixture
def engine():
    spec = importlib.util.spec_from_file_location("liveness_generation", ENGINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._validate_sudoers = lambda _path: None
    return module


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "vpn-liveness"
    path.mkdir(mode=0o700)
    return path


def candidate(root, generation=None):
    generation = generation or str(uuid4())
    stage = root / "staging" / generation
    stage.mkdir(parents=True, mode=0o700)
    stage.parent.chmod(0o700)
    (stage / "profiles").mkdir(mode=0o700)
    runner = "# fixture runner only\n"
    provenance = {"controller_revision": "a" * 40, "runner_sha256": hashlib.sha256(runner.encode()).hexdigest(),
                  "client_generation_id": str(uuid4()), "public_profile_digest": "b" * 64, "vantage": "external"}
    target_identity = {"inventory_alias": "vpn-p0-fixture", "public_service_address_sha256": "c" * 64,
                       "deployable_digest": "d" * 64, "applied_at": 1_700_000_000,
                       "required_profiles": ["p0-reality", "p1-xhttp"], "source_revision": "a" * 40,
                       "runner_sha256": provenance["runner_sha256"], "public_profile_digest": "b" * 64}
    files = {
        "runner.py": runner,
        "config.json": json.dumps({"schema_version": 2, "sentinel": "fixture-sentinel", "expected_runtime": {"sing_box": "1.12.0", "xray": "25.8.3"},
                                   "sing_box": {"config": str(root / "generations" / generation / "profiles/sing-box.json"), "profiles": {"p0-reality": [18080]}},
                                   "xray": {"config": str(root / "generations" / generation / "profiles/xray.json"), "profiles": {"p1-xhttp": [18180]}},
                                   "provenance": provenance, "target_identity": target_identity}),
        "metadata.json": json.dumps({
            "generation_id": generation,
            "required_profiles": ["p0-reality", "p1-xhttp"],
            "ssh_user": "deploy",
            "provenance": provenance,
            "target_identity": target_identity,
        }),
        "profiles/sing-box.json": '{"fixture": true}\n',
        "profiles/xray.json": '{"fixture": true}\n',
    }
    for name, content in files.items():
        path = stage / name
        path.write_text(content)
        path.chmod(0o600)
    return generation, stage


def healthy(directory):
    config = json.loads((directory / "config.json").read_text())
    return {
        "schema_version": 2, "sentinel": config["sentinel"], "runtime": config["expected_runtime"],
        "provenance": config["provenance"], "observed_at": int(time.time()),
        "target_identity": config["target_identity"],
        "control": {"verdict": "ok"},
        "profiles": [
            {"profile": "p0-reality", "verdict": "ok", "dns_through_tunnel": True, "authenticated_handshake": True},
            {"profile": "p1-xhttp", "verdict": "ok", "dns_through_tunnel": True, "authenticated_handshake": True},
        ],
    }


def test_generation_commits_after_probe_and_retry_does_not_probe_again(engine, root):
    generation, stage = candidate(root)
    calls = []

    def probe(directory):
        calls.append(directory)
        assert (root / "pending.json").is_file()
        assert (root / "current").resolve() == directory
        return healthy(directory)

    receipt = engine.install_generation(root, generation, stage, probe)
    assert receipt["generation_id"] == generation
    assert receipt["status"] == "committed"
    assert len(calls) == 1
    assert not (root / "pending.json").exists()
    installed = root / "generations" / generation
    assert (root / "current").readlink() == Path("generations") / generation
    assert (installed / "profiles/sing-box.json").read_text() == '{"fixture": true}\n'
    assert not (installed / "runner.py").stat().st_mode & 0o222
    assert engine.install_generation(root, generation, stage, probe) == receipt
    assert len(calls) == 1


def test_oversized_rollback_snapshot_is_rejected_before_bootstrap_mutation(engine, root, monkeypatch):
    generation, stage = candidate(root)
    monkeypatch.setattr(engine, "MAX_FILE", 65536)
    previous = {}
    for target in engine.BOOTSTRAP:
        path = engine._host_path(root, target)
        content = b"previous installation\n" * 1000
        engine._write(path, content, 0o644)
        previous[path] = content
    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, lambda _p: pytest.fail("must refuse oversized rollback before probe"))
    assert all(path.read_bytes() == content for path, content in previous.items())
    assert not (root / "current").exists()
    assert not (root / "pending.json").exists()


@pytest.mark.parametrize("toolchain", ["c" * 64, "invalid", None])
def test_awg_generation_requires_immutable_toolchain_pin(engine, root, toolchain):
    generation, stage = candidate(root)
    config_path = stage / "config.json"
    config = json.loads(config_path.read_text())
    config["amneziawg"] = {"config": str(root / "generations" / generation / "profiles/awg.conf"), "address": "10.66.66.2/32"}
    config["expected_runtime"]["awg"] = "1.0.0"
    if toolchain is not None:
        config["expected_runtime"]["awg_toolchain"] = toolchain
    config_path.write_text(json.dumps(config))
    metadata_path = stage / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["required_profiles"].append("p2-amneziawg")
    metadata["target_identity"]["required_profiles"] = sorted(metadata["required_profiles"])
    metadata_path.write_text(json.dumps(metadata))
    config["target_identity"] = metadata["target_identity"]
    config_path.write_text(json.dumps(config))
    profile = stage / "profiles/awg.conf"
    profile.write_text("fixture only\n")
    profile.chmod(0o600)

    def probe(directory):
        report = healthy(directory)
        report["profiles"].append({"profile": "p2-amneziawg", "verdict": "ok", "dns_through_tunnel": True,
                                   "authenticated_handshake": True, "fresh_handshake": True})
        return report

    if toolchain == "c" * 64:
        assert engine.install_generation(root, generation, stage, probe)["status"] == "committed"
    else:
        with pytest.raises(engine.GenerationError, match="candidate-runtime"):
            engine.install_generation(root, generation, stage, probe)


def test_rollback_deletions_are_durable_before_pending_disappears(engine, root, monkeypatch):
    generation, stage = candidate(root)
    events = []
    original_unlink, original_sync = Path.unlink, engine._sync

    def unlink(path, *args, **kwargs):
        events.append(("unlink", path))
        return original_unlink(path, *args, **kwargs)

    def sync(path):
        events.append(("sync", path))
        return original_sync(path)

    def fail(directory):
        engine._save(root / "receipts" / f"{generation}.json", {})
        events.clear()
        raise RuntimeError("fixture interruption after receipt creation")

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(engine, "_sync", sync)
    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, fail)
    terminal = events.index(("unlink", root / "pending.json"))
    deleted = [engine._host_path(root, path) for path in engine.BOOTSTRAP]
    deleted.append(root / "receipts" / f"{generation}.json")
    for path in deleted:
        index = events.index(("unlink", path))
        assert ("sync", path.parent) in events[index + 1:terminal]
    assert not (root / "pending.json").exists()


@pytest.mark.parametrize("failure", ["control", "missing-profile", "duplicate-profile", "exception"])
def test_failed_initial_probe_restores_previous_generation(engine, root, failure):
    previous, stage = candidate(root)
    engine.install_generation(root, previous, stage, healthy)
    generation, stage = candidate(root)

    def probe(directory):
        if failure == "exception":
            raise RuntimeError("fixture probe failure")
        result = healthy(directory)
        if failure == "control":
            result["control"]["verdict"] = "error"
        elif failure == "missing-profile":
            result["profiles"].pop()
        else:
            result["profiles"].append(result["profiles"][0].copy())
        return result

    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, probe)
    assert (root / "current").readlink() == Path("generations") / previous
    assert not (root / "pending.json").exists()


@pytest.mark.parametrize("invalid", ["symlink", "hardlink", "world-readable", "identity"])
def test_invalid_candidate_cannot_change_current_or_invoke_probe(engine, root, invalid):
    generation, stage = candidate(root)
    profile = stage / "profiles/sing-box.json"
    if invalid == "symlink":
        profile.unlink()
        profile.symlink_to(stage / "config.json")
    elif invalid == "hardlink":
        profile.unlink()
        os.link(stage / "config.json", profile)
    elif invalid == "world-readable":
        profile.chmod(0o644)
    else:
        generation = "../../outside"

    def never_probe(_directory):
        pytest.fail("invalid candidate reached probe")

    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, never_probe)
    assert not (root / "current").exists()
    assert not (root / "pending.json").exists()


def test_bad_pending_receipt_blocks_run_without_probing(engine, root):
    generation, stage = candidate(root)
    engine.install_generation(root, generation, stage, healthy)
    pending = root / "pending.json"
    pending.write_text('{"previous": "../../outside"}\n')
    pending.chmod(0o600)
    with pytest.raises(engine.GenerationError):
        engine.run_current(root, healthy)
    assert pending.exists()
    assert (root / "current").readlink() == Path("generations") / generation


def bootstrap_files(engine, root):
    return [engine._host_path(root, target) for target in engine.BOOTSTRAP]


@pytest.mark.parametrize("previous_exists", [False, True])
def test_failure_restores_all_bootstrap_bytes_modes_and_absences(engine, root, previous_exists):
    if previous_exists:
        previous, stage = candidate(root)
        engine.install_generation(root, previous, stage, healthy)
        for index, path in enumerate(bootstrap_files(engine, root)):
            path.chmod(0o600)
            path.write_bytes(f"prior bootstrap {index}\n".encode())
            path.chmod(0o640 if index == 2 else 0o744)
    before = [(p.read_bytes(), p.stat().st_mode & 0o777) if p.exists() else None for p in bootstrap_files(engine, root)]
    generation, stage = candidate(root)
    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, lambda _path: {})
    after = [(p.read_bytes(), p.stat().st_mode & 0o777) if p.exists() else None for p in bootstrap_files(engine, root)]
    assert after == before
    assert (root / "current").exists() == previous_exists
    assert engine.install_generation(root, generation, stage, healthy)["status"] == "committed"


def test_install_run_and_recovery_share_one_exclusive_lock(engine, root):
    generation, stage = candidate(root)

    def probe(directory):
        for action in (lambda: engine.run_current(root, healthy), lambda: engine.recover_pending(root)):
            with pytest.raises(engine.GenerationError, match="busy"):
                action()
        return healthy(directory)

    engine.install_generation(root, generation, stage, probe)
    assert engine.run_current(root, healthy)["control"]["verdict"] == "ok"


def test_next_run_recovers_hard_interruption_before_probing(engine, root):
    previous, stage = candidate(root)
    engine.install_generation(root, previous, stage, healthy)
    original = [p.read_bytes() for p in bootstrap_files(engine, root)]
    generation, stage = candidate(root)
    code = """
import importlib.util, os, pathlib, sys
spec = importlib.util.spec_from_file_location('fixture_engine', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._validate_sudoers = lambda path: None
module.install_generation(pathlib.Path(sys.argv[2]), sys.argv[3], pathlib.Path(sys.argv[4]), lambda path: os._exit(86))
"""
    child = subprocess.run([sys.executable, "-B", "-c", code, str(ENGINE), str(root), generation, str(stage)], timeout=10, check=False)
    assert child.returncode == 86
    assert (root / "pending.json").is_file()
    assert (root / "current").readlink() == Path("generations") / generation

    def after_recovery(directory):
        assert directory.name == previous
        assert not (root / "pending.json").exists()
        assert [p.read_bytes() for p in bootstrap_files(engine, root)] == original
        return healthy(directory)

    engine.run_current(root, after_recovery)
    assert engine.install_generation(root, generation, stage, healthy)["status"] == "committed"


def test_sudoers_validation_precedes_bootstrap_and_activation(engine, root):
    generation, stage = candidate(root)

    def invalid(_path):
        raise engine.GenerationError("fixture-sudoers-invalid")

    engine._validate_sudoers = invalid
    with pytest.raises(engine.GenerationError, match="fixture-sudoers-invalid"):
        engine.install_generation(root, generation, stage, healthy)
    assert not (root / "pending.json").exists()
    assert not (root / "current").exists()
    assert all(not p.exists() for p in bootstrap_files(engine, root))


def test_committed_retry_rejects_changed_candidate(engine, root):
    generation, stage = candidate(root)
    engine.install_generation(root, generation, stage, healthy)
    (stage / "profiles/sing-box.json").write_text('{"fixture": "changed"}\n')
    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, healthy)


def test_fixed_launcher_rejects_arguments_and_sudoers_has_empty_args(engine, root):
    generation, stage = candidate(root)
    engine.install_generation(root, generation, stage, healthy)
    _, launcher, sudoers = bootstrap_files(engine, root)
    result = subprocess.run([launcher, "--config", "/tmp/unsafe"], check=False, timeout=5)
    assert result.returncode == 2
    assert sudoers.read_text() == 'deploy ALL=(root) NOPASSWD: /usr/local/sbin/vpn-protocol-liveness ""\n'
    assert " -I -B -S /usr/local/lib/vpn-liveness/liveness_generation.py run" in launcher.read_text()


def test_generated_sudoers_passes_the_real_system_parser(engine, root):
    generation, stage = candidate(root)
    engine.install_generation(root, generation, stage, healthy)
    sudoers = bootstrap_files(engine, root)[2]
    result = subprocess.run(["/usr/sbin/visudo", "-cf", str(sudoers)], capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize("kind", ["timeout", "overflow", "failure"])
def test_bounded_fixed_command_fails_closed(engine, kind):
    code = {"timeout": "import time; time.sleep(10)", "overflow": "print('x' * 1048577)", "failure": "raise SystemExit(1)"}[kind]
    with pytest.raises(engine.GenerationError):
        engine._command([sys.executable, "-B", "-c", code], 0.1 if kind == "timeout" else 5)


@pytest.mark.parametrize("timeout,profiles,expected", [(60, sorted({"p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"}), 540),
    (15, ["p0-reality"], 270), (1, ["p1-xhttp", "p2-hysteria2"], 243)])
def test_shared_probe_deadline_covers_each_logical_profile(engine, timeout, profiles, expected):
    assert engine.probe_deadline(timeout, profiles) == expected
    assert expected < engine.JOB_TIMEOUT_SECONDS < engine.RECEIPT_TIMEOUT


@pytest.mark.parametrize("timeout,profiles", [(True, ["p0-reality"]), (0, ["p0-reality"]),
    (61, ["p0-reality"]), ("60", ["p0-reality"]), (15, []), (15, ["unknown"]),
    (15, ["p0-reality", "p0-reality"]), (15, [["p0-reality"]]), (15, "p0-reality")])
def test_shared_probe_deadline_rejects_invalid_inputs(engine, timeout, profiles):
    with pytest.raises(engine.GenerationError):
        engine.probe_deadline(timeout, profiles)


def test_initial_probe_uses_candidate_maximum_deadline(engine, root, monkeypatch):
    _, stage = candidate(root)
    config = json.loads((stage / "config.json").read_text())
    config["timeout_seconds"] = 60
    (stage / "config.json").write_text(json.dumps(config))
    metadata = json.loads((stage / "metadata.json").read_text())
    metadata["required_profiles"] = sorted(engine.PROFILES)
    (stage / "metadata.json").write_text(json.dumps(metadata))
    observed = []
    def command(argv, timeout):
        observed.append((argv, timeout))
        return b'{"fixture":true}'
    monkeypatch.setattr(engine, "_command", command)
    assert engine._probe(stage) == {"fixture": True}
    assert observed[0][1] == 540
    assert observed[0][0][-2:] == ["--config", str(stage / "config.json")]


def test_copy_failure_leaves_no_partial_generation_and_retry_succeeds(engine, root, monkeypatch):
    generation, stage = candidate(root)
    write = engine._write

    def fail_profile_copy(path, *args, **kwargs):
        if path.name == "sing-box.json" and "generations" in path.parts:
            raise OSError("fixture full disk")
        return write(path, *args, **kwargs)

    monkeypatch.setattr(engine, "_write", fail_profile_copy)
    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, healthy)
    assert not (root / "pending.json").exists()
    assert not (root / "current").exists()
    assert not list((root / "generations").iterdir())
    monkeypatch.setattr(engine, "_write", write)
    assert engine.install_generation(root, generation, stage, healthy)["status"] == "committed"


@pytest.mark.parametrize("field", ["controller_revision", "runner_sha256", "client_generation_id", "public_profile_digest", "vantage"])
def test_provenance_requires_typed_complete_bound_values(engine, root, field):
    generation, stage = candidate(root)
    metadata = json.loads((stage / "metadata.json").read_text())
    metadata["provenance"][field] = "unapproved-value"
    (stage / "metadata.json").write_text(json.dumps(metadata))
    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, healthy)
    assert not (root / "current").exists()


@pytest.mark.parametrize("field", ["schema_version", "sentinel", "runtime", "provenance", "observed_at", "future"])
def test_initial_report_must_bind_generation_identity_runtime_and_time(engine, root, field):
    generation, stage = candidate(root)

    def bad_report(directory):
        report = healthy(directory)
        if field == "future":
            report["observed_at"] = int(time.time()) + 600
        elif field == "observed_at":
            report[field] = 1
        elif field == "schema_version":
            report[field] = 1
        elif field in {"runtime", "provenance"}:
            report[field] = {}
        else:
            report[field] = "other-sentinel"
        return report

    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, bad_report)
    assert not (root / "current").exists()


def test_candidate_requires_each_runtime_section_and_exact_profile_set(engine, root):
    generation, stage = candidate(root)
    config = json.loads((stage / "config.json").read_text())
    del config["xray"]
    (stage / "config.json").write_text(json.dumps(config))
    with pytest.raises(engine.GenerationError):
        engine.install_generation(root, generation, stage, healthy)


def test_read_rejects_a_writable_ancestor_above_a_private_leaf(engine, tmp_path):
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o700)
    leaf = unsafe / "private"
    leaf.mkdir(mode=0o700)
    source = leaf / "value"
    source.write_text("private fixture")
    source.chmod(0o600)
    unsafe.chmod(0o777)
    with pytest.raises(engine.GenerationError):
        engine._read(source)


def test_receipt_reconciliation_needs_no_stage_or_probe(engine, root):
    generation, stage = candidate(root)
    receipt = engine.install_generation(root, generation, stage, healthy)
    stage.rename(stage.with_name("stage-removed"))
    assert engine.committed_receipt(root, generation) == receipt


@pytest.mark.parametrize("state,code", [("absent", 3), ("busy", 75), ("corrupt", 1)])
def test_receipt_cli_distinguishes_absence_busy_and_corruption(engine, root, monkeypatch, state, code):
    generation = str(uuid4())
    monkeypatch.setattr(engine, "ROOT", root)
    monkeypatch.setattr(engine.os, "geteuid", os.getuid)
    # CLI authority is tested separately; this case exercises error classification.
    original_uid = engine.os.geteuid
    monkeypatch.setattr(engine.os, "geteuid", lambda: 0)
    def receipt(_root, _generation):
        monkeypatch.setattr(engine.os, "geteuid", original_uid)
        if state == "busy":
            raise engine.GenerationError("busy")
        if state == "corrupt":
            raise engine.GenerationError("state-invalid")
        return actual(_root, _generation)
    actual = engine.committed_receipt
    monkeypatch.setattr(engine, "committed_receipt", receipt)
    monkeypatch.setattr(sys, "argv", ["engine", "receipt", generation])
    assert engine.main() == code


def test_missing_receipt_does_not_hide_corrupt_current(engine, root):
    (root / "current").symlink_to("generations/" + str(uuid4()))
    with pytest.raises((engine.GenerationError, OSError)) as caught:
        engine.committed_receipt(root, str(uuid4()))
    assert str(caught.value) != "generation-uncommitted"


@pytest.mark.parametrize("action", ["retry", "run", "receipt"])
@pytest.mark.parametrize("mutation", ["provenance", "target"])
def test_receipt_public_identity_must_match_installed_candidate(engine, root, action, mutation):
    generation, stage = candidate(root)
    engine.install_generation(root, generation, stage, healthy)
    path = root / "receipts" / f"{generation}.json"
    receipt = json.loads(path.read_text())
    if mutation == "provenance":
        receipt["provenance"]["public_profile_digest"] = "c" * 64
    else:
        receipt["target_identity"]["deployable_digest"] = "e" * 64
    path.write_text(json.dumps(receipt))
    with pytest.raises(engine.GenerationError):
        if action == "retry":
            engine.install_generation(root, generation, stage, healthy)
        elif action == "run":
            engine.run_current(root, healthy)
        else:
            engine.committed_receipt(root, generation)
