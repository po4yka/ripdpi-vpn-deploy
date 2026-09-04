from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/disposable_liveness_executor.py"


def load_module():
    spec = importlib.util.spec_from_file_location("disposable_executor", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Runner:
    def __init__(self, home: Path):
        self.home = home
        self.calls: list[tuple[str, ...]] = []
        self.context = "default"
        self.mounts = b"/dev/root on / type ext4 (rw)\n"
        self.systemd = b"systemd\n"
        self.secrets = None
        self.executor_marker = None
        self.secret_edits = False
        self.profile_status = "Running"
        self.delete_fail_once = False

    def __call__(self, argv, *, timeout=30, input_bytes=b"", environment=None):
        command = tuple(argv)
        self.calls.append(command)
        if command[:3] == ("docker", "context", "show"):
            return (self.context + "\n").encode()
        if command[:2] == ("colima", "start"):
            profile = command[command.index("--profile") + 1]
            root = self.home / ".colima" / profile
            root.mkdir(parents=True)
            (root / "colima.yaml").write_text(
                yaml.safe_dump(
                    {
                        "autoActivate": False,
                        "mounts": [],
                        "network": {
                            "address": False,
                            "mode": "shared",
                        },
                        "portForwarder": "none",
                        "sshConfig": False,
                    }
                )
            )
            (root / "colima.yaml").chmod(0o600)
            return b""
        if len(command) >= 4 and command[:3] == ("colima", "status", "--profile"):
            profile = command[3]
            return json.dumps(
                {
                    "name": profile,
                    "status": self.profile_status,
                    "arch": "aarch64",
                    "runtime": "docker",
                }
            ).encode()
        if command[:3] == ("colima", "list", "--json"):
            profile = next(
                path.name for path in (self.home / ".colima").iterdir() if path.is_dir()
            )
            return (
                json.dumps(
                    {
                        "name": profile,
                        "status": self.profile_status,
                        "arch": "aarch64",
                        "runtime": "docker",
                    }
                )
                + "\n"
            ).encode()
        if command[:3] == ("colima", "ssh", "--profile"):
            if command[-1] == "mount":
                return self.mounts
            if "ps" in command and "comm=" in command:
                return self.systemd
            if "vpn-liveness-executor-id" in " ".join(command):
                if command[-1] != "/var/lib/vpn-liveness-executor-id":
                    self.executor_marker = command[-1]
                    return b""
                assert self.executor_marker is not None
                return (self.executor_marker + "\n").encode()
            return b""
        if command[:3] == ("colima", "stop", "--profile"):
            self.profile_status = "Stopped"
            return b""
        if command[:3] == ("colima", "delete", "--profile"):
            if self.delete_fail_once:
                self.delete_fail_once = False
                raise RuntimeError("fixture delete failure")
            profile = command[3]
            root = self.home / ".colima" / profile
            for child in root.iterdir():
                child.unlink()
            root.rmdir()
            return b""
        if command[:2] == ("sops", "--decrypt"):
            assert self.secrets is not None
            value = json.loads(json.dumps(self.secrets))
            if self.secret_edits:
                for root, field in (
                    ("xray", "clients"),
                    ("hysteria", "clients"),
                    ("amneziawg_secrets", "peers"),
                ):
                    value[root][field] = []
                value["snell_secrets"]["variants"][0]["users"] = []
                value["client_registry"] = {}
            return yaml.safe_dump(value).encode()
        if command[:2] == ("sops", "unset"):
            target = Path(command[-2])
            assert target.stat().st_mode & 0o777 == 0o600
            target.write_bytes(target.read_bytes() + b"# edited\n")
            self.secret_edits = True
            return b""
        if Path(command[0]).name == "audit-log.sh":
            return b""
        raise AssertionError(command)


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUILD_GATE_HELD", "1")
    module = load_module()
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    evidence = tmp_path / "private"
    evidence.mkdir(mode=0o700)
    runner = Runner(home)
    return module, home, evidence, runner


def test_prepare_creates_private_bound_nondefault_profile_manifest(setup):
    module, home, evidence, runner = setup
    manifest_path = evidence / "executor.json"

    manifest = module.prepare_executor(
        profile="vpn-liveness-one-shot",
        manifest_path=manifest_path,
        home=home,
        now=1_700_000_000,
        expires_at=1_700_003_600,
        runner=runner,
    )

    assert manifest["profile"] == "vpn-liveness-one-shot"
    assert manifest["kind"] == "colima-systemd"
    assert manifest["initial_docker_context"] == "default"
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(manifest_path.read_text()) == manifest
    start = next(call for call in runner.calls if call[:2] == ("colima", "start"))
    assert "--activate=false" in start
    assert "--network-address=false" in start
    assert "--ssh-config=false" in start
    for flag, value in (
        ("--mount", "none"),
        ("--network-mode", "shared"),
        ("--port-forwarder", "none"),
    ):
        assert start[start.index(flag) + 1] == value


def test_private_json_io_handles_short_syscalls(setup, monkeypatch):
    module, _, evidence, _ = setup
    document = {"schema_version": 1, "value": "bounded"}
    path = evidence / "short-io.json"
    real_write = module.os.write
    real_read = module.os.read

    def short_write(descriptor, payload):
        return real_write(descriptor, payload[:1])

    monkeypatch.setattr(module.os, "write", short_write)
    module._write_new(path, document)
    monkeypatch.setattr(module.os, "write", real_write)

    def short_read(descriptor, size):
        return real_read(descriptor, min(size, 1))

    monkeypatch.setattr(module.os, "read", short_read)
    assert module._read_private(path)[0] == document


def test_failed_private_json_write_removes_only_its_partial_file(setup, monkeypatch):
    module, _, evidence, _ = setup
    path = evidence / "partial.json"
    real_write = module.os.write

    def fail_after_one_byte(descriptor, payload):
        if os.fstat(descriptor).st_size:
            raise OSError("fixture write failure")
        return real_write(descriptor, payload[:1])

    monkeypatch.setattr(module.os, "write", fail_after_one_byte)
    with pytest.raises(OSError, match="fixture write failure"):
        module._write_new(path, {"schema_version": 1})
    assert not path.exists()


def test_rejected_lock_closes_the_open_descriptor(setup, monkeypatch):
    module, _, evidence, _ = setup
    lock = evidence / "unsafe.lock"
    lock.write_text("")
    lock.chmod(0o644)
    real_close = module.os.close
    closed = []

    def record_close(descriptor):
        closed.append(descriptor)
        return real_close(descriptor)

    monkeypatch.setattr(module.os, "close", record_close)
    with pytest.raises(module.ExecutorError, match="deonboard-lock"):
        with module._exclusive_locks((lock,)):
            pass
    assert len(closed) == 1


@pytest.mark.parametrize("profile", ["default", "colima", "vpn-ssh-ci-20260828"])
def test_prepare_refuses_default_or_shared_profile_before_start(setup, profile):
    module, home, evidence, runner = setup
    with pytest.raises(module.ExecutorError, match="profile-name"):
        module.prepare_executor(
            profile=profile,
            manifest_path=evidence / "executor.json",
            home=home,
            now=1_700_000_000,
            expires_at=1_700_003_600,
            runner=runner,
        )
    assert not runner.calls


def test_prepare_failure_deletes_only_claimed_profile_and_keeps_context(setup):
    module, home, evidence, runner = setup
    runner.mounts = b"host on /Users/operator type virtiofs (rw)\n"

    with pytest.raises(module.ExecutorError, match="executor-mount"):
        module.prepare_executor(
            profile="vpn-liveness-one-shot",
            manifest_path=evidence / "executor.json",
            home=home,
            now=1_700_000_000,
            expires_at=1_700_003_600,
            runner=runner,
        )

    assert not (home / ".colima/vpn-liveness-one-shot").exists()
    assert not (evidence / "executor.json").exists()
    assert runner.context == "default"


@pytest.mark.parametrize("drift", ["mount", "context", "config"])
def test_live_verification_refuses_mount_port_or_context_drift(setup, drift):
    module, home, evidence, runner = setup
    manifest_path = evidence / "executor.json"
    module.prepare_executor(
        profile="vpn-liveness-one-shot",
        manifest_path=manifest_path,
        home=home,
        now=1_700_000_000,
        expires_at=1_700_003_600,
        runner=runner,
    )
    if drift == "mount":
        runner.mounts += b"host on /Users/operator type virtiofs (rw)\n"
    elif drift == "context":
        runner.context = "colima"
    else:
        config = home / ".colima/vpn-liveness-one-shot/colima.yaml"
        doc = yaml.safe_load(config.read_text())
        doc["portForwarder"] = "ssh"
        config.write_text(yaml.safe_dump(doc))
        config.chmod(0o600)

    with pytest.raises(module.ExecutorError, match=f"executor-{drift}"):
        module.load_live_executor(
            manifest_path, home=home, now=1_700_000_001, runner=runner
        )


def test_nested_port_forwarder_cannot_authorize_missing_or_active_top_level(setup):
    module, home, evidence, runner = setup
    profile = "vpn-liveness-one-shot"
    module.prepare_executor(
        profile=profile,
        manifest_path=evidence / "executor.json",
        home=home,
        now=1_700_000_000,
        expires_at=1_700_003_600,
        runner=runner,
    )
    config = home / ".colima" / profile / "colima.yaml"
    doc = yaml.safe_load(config.read_text())
    # Colima's effective setting is top-level; a nested lookalike has no authority.
    doc["network"]["portForwarder"] = "none"
    for forwarder in (None, "ssh", "grpc"):
        if forwarder is None:
            doc.pop("portForwarder", None)
        else:
            doc["portForwarder"] = forwarder
        config.write_text(yaml.safe_dump(doc))
        with pytest.raises(module.ExecutorError, match="executor-config"):
            module._config(home, profile)


def _identity():
    generation = "00000000-0000-4000-8000-000000000001"
    provenance = {
        "controller_revision": "a" * 40,
        "runner_sha256": "b" * 64,
        "client_generation_id": generation,
        "public_profile_digest": "c" * 64,
        "vantage": "external",
    }
    target = {
        "inventory_alias": "vpn-staging",
        "public_service_address_sha256": "d" * 64,
        "deployable_digest": "e" * 64,
        "applied_at": 1_700_000_000,
        "required_profiles": [
            "p0-reality",
            "p1-xhttp",
            "p2-amneziawg",
            "p2-hysteria2",
        ],
        "source_revision": "a" * 40,
        "runner_sha256": "b" * 64,
        "public_profile_digest": "c" * 64,
    }
    return generation, provenance, target


def test_binding_cross_links_executor_config_generation_and_report(setup):
    module, home, evidence, runner = setup
    manifest = evidence / "executor.json"
    binding = evidence / "binding.json"
    config = evidence / "liveness.yaml"
    cleanup = evidence / "cleanup-manifest.json"
    config.write_text("schema_version: 2\nsentinels:\n  - id: probe-a\n")
    config.chmod(0o600)
    cleanup.write_text('{"schema_version":2}\n')
    cleanup.chmod(0o600)
    module.prepare_executor(
        profile="vpn-liveness-one-shot",
        manifest_path=manifest,
        home=home,
        now=1_700_000_000,
        expires_at=1_700_003_600,
        runner=runner,
    )
    generation, provenance, target = _identity()

    document = module.bind_executor(
        manifest,
        binding,
        config,
        cleanup,
        sentinel="probe-a",
        client="liveness-a",
        generation_id=generation,
        provenance=provenance,
        target_identity=target,
        home=home,
        now=1_700_000_001,
        runner=runner,
    )

    assert (
        document["executor_manifest_sha256"]
        == hashlib.sha256(manifest.read_bytes()).hexdigest()
    )
    assert document["config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert binding.stat().st_mode & 0o777 == 0o600
    report = {
        "sentinel": "probe-a",
        "provenance": provenance,
        "target_identity": target,
    }
    assert module.verify_report_binding(binding, manifest, config, report) == {
        "kind": "colima-systemd",
        "executor_id_sha256": hashlib.sha256(
            document["executor_id"].encode("ascii")
        ).hexdigest(),
        "manifest_sha256": document["executor_manifest_sha256"],
    }
    report["provenance"] = {
        **provenance,
        "client_generation_id": "00000000-0000-4000-8000-000000000002",
    }
    with pytest.raises(module.ExecutorError, match="binding-report"):
        module.verify_report_binding(binding, manifest, config, report)


def test_binding_refuses_multi_sentinel_config_before_publication(setup):
    module, home, evidence, runner = setup
    manifest = evidence / "executor.json"
    binding = evidence / "binding.json"
    config = evidence / "liveness.yaml"
    cleanup = evidence / "cleanup-manifest.json"
    config.write_text(
        "schema_version: 2\nsentinels:\n  - id: probe-a\n  - id: probe-b\n"
    )
    config.chmod(0o600)
    cleanup.write_text('{"schema_version":2}\n')
    cleanup.chmod(0o600)
    module.prepare_executor(
        profile="vpn-liveness-one-shot",
        manifest_path=manifest,
        home=home,
        now=1_700_000_000,
        expires_at=1_700_003_600,
        runner=runner,
    )
    generation, provenance, target = _identity()

    with pytest.raises(module.ExecutorError, match="binding-config"):
        module.bind_executor(
            manifest,
            binding,
            config,
            cleanup,
            sentinel="probe-a",
            client="liveness-a",
            generation_id=generation,
            provenance=provenance,
            target_identity=target,
            home=home,
            now=1_700_000_001,
            runner=runner,
        )
    assert not binding.exists()


def test_deonboard_refuses_without_exact_provider_absence_before_mutation(setup):
    module, home, evidence, runner = setup
    registry = evidence / "registry.json"
    config = evidence / "liveness.yaml"
    sops_file = evidence / "secrets.sops.yaml"
    for path, payload in (
        (registry, b'{"schema_version":2,"sentinels":{}}\n'),
        (config, b"schema_version: 2\n"),
        (sops_file, b"encrypted-fixture\n"),
    ):
        path.write_bytes(payload)
        path.chmod(0o600)
    before = {path: path.read_bytes() for path in (registry, config, sops_file)}
    absence = evidence / "absence.json"
    absence.write_text(
        json.dumps(
            {
                "billing_status": "no-active-owned-resources",
                "root_storage_status": "absent",
                "schema_version": 2,
                "server_status": "absent",
                "status": "apply_started",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    absence.chmod(0o600)

    with pytest.raises(module.ExecutorError, match="target-absence"):
        module.deonboard(
            binding_path=evidence / "binding.json",
            manifest_path=evidence / "executor.json",
            absence_evidence_path=absence,
            registry_path=registry,
            config_path=config,
            sops_file=sops_file,
            output_path=evidence / "deonboard.json",
            home=home,
            runner=runner,
        )

    assert {path: path.read_bytes() for path in before} == before


def test_deonboard_refuses_partial_secret_state_with_only_snell_remaining(setup):
    module, _, _, _ = setup
    partial = {
        "xray": {"clients": []},
        "hysteria": {"clients": []},
        "amneziawg_secrets": {"peers": []},
        "snell_secrets": {"variants": [{"users": [{"name": "liveness-a"}]}]},
        "client_registry": {},
    }

    with pytest.raises(module.ExecutorError, match="deonboard-secrets"):
        module._client_secret_paths(partial, "liveness-a")


def test_deonboard_removes_only_exact_bound_local_executor_after_absence(setup):
    module, home, evidence, runner = setup
    manifest = evidence / "executor.json"
    binding = evidence / "binding.json"
    cleanup = evidence / "cleanup-manifest.json"
    config = evidence / "liveness.yaml"
    registry = evidence / "registry.json"
    sops_file = evidence / "secrets.sops.yaml"
    output = evidence / "deonboard.json"
    config_doc = {
        "schema_version": 2,
        "sentinels": [{"id": "probe-a"}],
    }
    config.write_text(yaml.safe_dump(config_doc))
    config.chmod(0o600)
    cleanup.write_text('{"schema_version":2}\n')
    cleanup.chmod(0o600)
    sops_file.write_text("encrypted\n")
    sops_file.chmod(0o600)
    runner.secrets = {
        "xray": {"clients": [{"name": "liveness-a"}]},
        "hysteria": {"clients": [{"name": "liveness-a"}]},
        "amneziawg_secrets": {"peers": [{"name": "liveness-a"}]},
        "snell_secrets": {"variants": [{"users": [{"name": "liveness-a"}]}]},
        "client_registry": {"liveness-a": {"status": "active"}},
    }
    module.prepare_executor(
        profile="vpn-liveness-one-shot",
        manifest_path=manifest,
        home=home,
        now=1_700_000_000,
        expires_at=1_700_003_600,
        runner=runner,
    )
    generation, provenance, target = _identity()
    bound = module.bind_executor(
        manifest,
        binding,
        config,
        cleanup,
        sentinel="probe-a",
        client="liveness-a",
        generation_id=generation,
        provenance=provenance,
        target_identity=target,
        home=home,
        now=1_700_000_001,
        runner=runner,
    )
    registry.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "sentinels": {
                    "probe-a": {
                        "client": "liveness-a",
                        "generation_id": generation,
                        "executor_binding_sha256": hashlib.sha256(
                            binding.read_bytes()
                        ).hexdigest(),
                    }
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    registry.chmod(0o600)
    absence = evidence / "absence.json"
    absence.write_text(
        json.dumps(
            {
                "billing_status": "no-active-owned-resources",
                "manifest_sha256": bound["cleanup_manifest_sha256"],
                "root_storage_status": "absent",
                "schema_version": 2,
                "server_status": "absent",
                "status": "verified",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    absence.chmod(0o600)

    runner.delete_fail_once = True
    with pytest.raises(RuntimeError, match="fixture delete failure"):
        module.deonboard(
            binding_path=binding,
            manifest_path=manifest,
            absence_evidence_path=absence,
            registry_path=registry,
            config_path=config,
            sops_file=sops_file,
            output_path=output,
            home=home,
            runner=runner,
        )
    assert runner.profile_status == "Stopped"
    assert not output.exists()

    result = module.deonboard(
        binding_path=binding,
        manifest_path=manifest,
        absence_evidence_path=absence,
        registry_path=registry,
        config_path=config,
        sops_file=sops_file,
        output_path=output,
        home=home,
        runner=runner,
    )

    assert result["status"] == "deonboarded"
    assert json.loads(registry.read_text()) == {"schema_version": 2, "sentinels": {}}
    assert not config.exists()
    assert not (home / ".colima/vpn-liveness-one-shot").exists()
    assert output.stat().st_mode & 0o777 == 0o600
    unset = [call[-1] for call in runner.calls if call[:2] == ("sops", "unset")]
    assert '["xray"]["clients"][0]' in unset
    assert '["client_registry"]["liveness-a"]' in unset

    assert (
        module.deonboard(
            binding_path=binding,
            manifest_path=manifest,
            absence_evidence_path=absence,
            registry_path=registry,
            config_path=config,
            sops_file=sops_file,
            output_path=output,
            home=home,
            runner=runner,
        )
        == result
    )
