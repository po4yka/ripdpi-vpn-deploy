"""Contract tests for the recurring real-VPS AWG/NAT lane."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import shlex
import subprocess
from pathlib import Path

import pytest

from scripts.template_render import merge_render_vars, render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "real-vps-awg-nat.py"
FIREWALL_TEMPLATE = REPO_ROOT / "ansible/roles/firewall/templates/nftables.conf.j2"


def load_module():
    spec = importlib.util.spec_from_file_location("real_vps_awg_nat", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


lane = load_module()


class FakeExecutor:
    def __init__(self, *, direct_ok: bool = True, fail_phase: str | None = None):
        self.direct_ok = direct_ok
        self.fail_phase = fail_phase
        self.calls: list[str] = []
        self.service_generation = "6" * 64
        self.config_generation = "7" * 64
        self.next_generation = "8" * 64
        self.current_peer = "9" * 64
        self.next_peer = "a" * 64
        self.current_client = {
            "clientConfigSha256": "b" * 64,
            "peerConfigSha256": self.current_peer,
        }
        self.rotated_client = {
            "clientConfigSha256": "c" * 64,
            "peerConfigSha256": self.next_peer,
        }
        self.active_peer: str | None = None
        self.latest_handshake = 1_999_999_900
        self.peer_rx = 0
        self.peer_tx = 0
        self.nat_packets = 0
        self.nat_bytes = 0
        self.reload_target = "next"
        self.capture_index = 0

    def _status(self) -> dict:
        return {
            "serviceActive": True,
            "interfaceUp": True,
            "deployedSourceSha": "1" * 40,
            "deployedArchiveSha256": "2" * 64,
            "serviceInvocationSha256": self.service_generation,
            "configGenerationSha256": self.config_generation,
            "peerConfigSha256": self.current_peer,
            "latestHandshakeEpoch": self.latest_handshake,
            "peerRxBytes": self.peer_rx,
            "peerTxBytes": self.peer_tx,
            "natPackets": self.nat_packets,
            "natBytes": self.nat_bytes,
        }

    @staticmethod
    def _probe(ok: bool = True) -> dict:
        return {
            "tcp": {"ok": ok, "durationMs": 8 if ok else None},
            "udp": {"ok": ok, "durationMs": 6 if ok else None},
        }

    def direct_probe(self) -> dict:
        self.calls.append("direct_probe")
        return self._probe(self.direct_ok)

    def deploy_source(self, source_sha: str, archive_sha256: str) -> dict:
        self.calls.append("deploy_source")
        return {
            "deployedSourceSha": source_sha,
            "deployedArchiveSha256": archive_sha256,
        }

    def client_evidence(self, *, rotated: bool) -> dict:
        self.calls.append(f"client_evidence:{str(rotated).lower()}")
        return dict(self.rotated_client if rotated else self.current_client)

    def server_status(self) -> dict:
        self.calls.append("server_status")
        return self._status()

    def start_client(self, *, rotated: bool) -> None:
        self.calls.append(f"start_client:{str(rotated).lower()}")
        self.active_peer = (self.rotated_client if rotated else self.current_client)[
            "peerConfigSha256"
        ]

    def probe(self, phase: str) -> dict:
        self.calls.append(f"probe:{phase}")
        ok = phase != self.fail_phase and self.active_peer == self.current_peer
        if ok:
            self.latest_handshake += 1
            self.peer_rx += 10
            self.peer_tx += 11
            self.nat_packets += 2
            self.nat_bytes += 200
        return self._probe(ok)

    def probe_once(self, phase: str) -> dict:
        self.calls.append(f"probe_once:{phase}")
        return self.probe(phase)

    def server_action(self, action: str) -> None:
        self.calls.append(f"server_action:{action}")
        if action == "restart":
            self.service_generation = "d" * 64
        elif self.reload_target == "next":
            self.config_generation = self.next_generation
            self.current_peer = self.next_peer
        else:
            self.config_generation = "7" * 64
            self.current_peer = "9" * 64

    def stage_rotation(self) -> dict:
        self.calls.append("stage_rotation")
        return {
            "previousConfigGenerationSha256": "7" * 64,
            "nextConfigGenerationSha256": self.next_generation,
            "previousPeerConfigSha256": "9" * 64,
            "nextPeerConfigSha256": self.next_peer,
            "rotatedClientConfigSha256": self.rotated_client["clientConfigSha256"],
        }

    def finalize_rotation(self, action: str) -> dict:
        self.calls.append(f"finalize_rotation:{action}")
        if action == "commit":
            self.current_client = dict(self.rotated_client)
            return {
                "action": action,
                "configGenerationSha256": self.next_generation,
                "peerConfigSha256": self.next_peer,
                "currentClientConfigSha256": self.current_client["clientConfigSha256"],
            }
        self.reload_target = "previous"
        return {
            "action": action,
            "configGenerationSha256": "7" * 64,
            "peerConfigSha256": "9" * 64,
            "currentClientConfigSha256": self.current_client["clientConfigSha256"],
        }

    def stop_client(self) -> str:
        self.calls.append("stop_client")
        self.active_peer = None
        self.capture_index += 1
        return format(self.capture_index, "x") * 64

    def close(self) -> None:
        self.calls.append("close")


def metadata() -> dict:
    return {
        "sourceSha": "1" * 40,
        "sourceArchiveSha256": "2" * 64,
        "executor": "github_actions",
        "entrypointPath": lane.WORKFLOW_PATH,
        "invocationId": "42",
        "invocationAttempt": 1,
    }


def config() -> dict:
    return {
        "clientIdentity": {
            "ripdpiSourceSha": "d" * 40,
            "artifactSha256": "e" * 64,
        },
        "runnerIdSha256": "2" * 64,
        "serverControlHookSha256": "5" * 64,
        "serverDeployHookSha256": "6" * 64,
        "rotationHookSha256": "3" * 64,
        "producerSha256": "4" * 64,
    }


def write_private_runner_config(
    tmp_path: Path,
    *,
    current_contents: str | None = None,
    rotated_contents: str | None = None,
    omit_current: bool = False,
    omit_rotated: bool = False,
    include_client_identity: bool = True,
) -> tuple[Path, Path]:
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    control = tmp_path / "control"
    deploy = tmp_path / "deploy"
    rotation = tmp_path / "rotation"
    valid_current = "\n".join(
        (
            "[Interface]",
            f"PrivateKey = {'A' * 43}=",
            "[Peer]",
            f"PublicKey = {'B' * 43}=",
            f"PresharedKey = {'B' * 43}=",
            "",
        )
    )
    valid_rotated = "\n".join(
        (
            "[Interface]",
            f"PrivateKey = {'C' * 43}=",
            "[Peer]",
            f"PublicKey = {'B' * 43}=",
            f"PresharedKey = {'E' * 43}=",
            "",
        )
    )
    for path, contents, mode, omitted in (
        (current, current_contents, 0o600, omit_current),
        (rotated, rotated_contents, 0o600, omit_rotated),
        (control, "private\n", 0o700, False),
        (deploy, "private\n", 0o700, False),
        (rotation, "private\n", 0o700, False),
    ):
        if not omitted:
            default_contents = valid_rotated if path == rotated else valid_current
            path.write_text(default_contents if contents is None else contents)
            path.chmod(mode)
    config_path = tmp_path / "runner.json"
    client_identity = tmp_path / lane.CLIENT_IDENTITY_DESCRIPTOR_NAME
    if include_client_identity:
        client_identity.write_text(
            json.dumps(
                {
                    "version": "ripdpi_awg_client_identity_v1",
                    "ripdpiSourceSha": "d" * 40,
                    "artifactSha256": "e" * 64,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        client_identity.chmod(0o600)
    value = {
        "version": lane.CONFIG_VERSION,
        "runnerId": "a" * 64,
        "clientConfigPath": str(current),
        "rotatedClientConfigPath": str(rotated),
        "clientAddress": "10.66.66.2/32",
        "tcpEchoAddress": "93.184.216.34",
        "tcpEchoPort": 10001,
        "udpEchoAddress": "151.101.1.69",
        "udpEchoPort": 10002,
        "serverControlHook": str(control),
        "serverDeployHook": str(deploy),
        "rotationHook": str(rotation),
        "probeTimeoutSeconds": 5,
        "recoveryTimeoutSeconds": 30,
        "deployTimeoutSeconds": 600,
    }
    config_path.write_text(json.dumps(value))
    config_path.chmod(0o600)
    source_archive = tmp_path / "source.tar"
    source_archive.write_bytes(b"source")
    return config_path, source_archive


def test_private_client_identity_descriptor_is_required_and_bound(
    tmp_path: Path,
) -> None:
    config_path, _source_archive = write_private_runner_config(
        tmp_path, include_client_identity=True
    )

    loaded = lane.load_config(config_path)

    assert loaded["clientIdentity"] == {
        "ripdpiSourceSha": "d" * 40,
        "artifactSha256": "e" * 64,
    }


def test_client_identity_descriptor_missing_or_symlink_fails_closed(
    tmp_path: Path,
) -> None:
    config_path, source_archive = write_private_runner_config(
        tmp_path, include_client_identity=False
    )
    manifest = run_with_private_config(
        config_path, source_archive, tmp_path / "out.json"
    )
    assert manifest["classification"] == "INFRA_UNAVAILABLE"
    assert manifest["reasonCode"] == "CONFIG_INVALID"
    assert manifest["clientIdentity"] == {
        "ripdpiSourceSha": "0" * 40,
        "artifactSha256": "0" * 64,
    }

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    config_path, _source_archive = write_private_runner_config(symlink_root)
    descriptor = config_path.parent / lane.CLIENT_IDENTITY_DESCRIPTOR_NAME
    replacement = config_path.parent / "replacement.json"
    replacement.write_text(descriptor.read_text())
    replacement.chmod(0o600)
    descriptor.unlink()
    descriptor.symlink_to(replacement)
    with pytest.raises(ValueError, match="absolute regular file"):
        lane.load_config(config_path)


def test_client_identity_descriptor_rejects_replaced_valid_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = tmp_path / lane.CLIENT_IDENTITY_DESCRIPTOR_NAME
    original = {
        "version": lane.CLIENT_IDENTITY_VERSION,
        "ripdpiSourceSha": "d" * 40,
        "artifactSha256": "e" * 64,
    }
    replacement = {
        "version": lane.CLIENT_IDENTITY_VERSION,
        "ripdpiSourceSha": "a" * 40,
        "artifactSha256": "b" * 64,
    }
    descriptor.write_text(json.dumps(original))
    descriptor.chmod(0o600)
    swapped = tmp_path / "replacement.json"
    swapped.write_text(json.dumps(replacement))
    swapped.chmod(0o600)
    real_open = os.open

    def replacing_open(path, flags, mode=0o777):
        if Path(path) == descriptor:
            os.replace(swapped, descriptor)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", replacing_open)
    with pytest.raises(ValueError, match="descriptor is unavailable"):
        lane.client_identity_descriptor(str(descriptor))


def test_client_identity_requires_manifest_v3() -> None:
    assert lane.MANIFEST_VERSION == "real_vps_awg_nat_evidence_v3"
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    lane.validate_manifest(manifest, expected_source_sha="1" * 40, now=2_000_000_000)
    manifest["version"] = "real_vps_awg_nat_evidence_v2"
    with pytest.raises(ValueError, match="unsupported manifest version"):
        lane.validate_manifest(
            manifest, expected_source_sha="1" * 40, now=2_000_000_000
        )


def test_loaded_client_identity_is_retained_in_preflight_failure(
    tmp_path: Path,
) -> None:
    config_path, source_archive = write_private_runner_config(tmp_path)
    manifest = run_with_private_config(
        config_path, source_archive, tmp_path / "out.json"
    )

    assert manifest["classification"] == "INFRA_UNAVAILABLE"
    assert manifest["reasonCode"] == "PREREQUISITE_MISSING"
    assert manifest["clientIdentity"] == {
        "ripdpiSourceSha": "d" * 40,
        "artifactSha256": "e" * 64,
    }


def test_loaded_client_identity_is_retained_when_executor_start_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path, source_archive = write_private_runner_config(tmp_path)
    loaded = lane.load_config(config_path)
    monkeypatch.setattr(lane, "load_config", lambda _path: loaded)
    monkeypatch.setattr(lane.os, "geteuid", lambda: 0)
    monkeypatch.setattr(lane.shutil, "which", lambda _command: "/usr/bin/tool")

    class FailedExecutor:
        def __init__(self, _config: dict) -> None:
            raise OSError("fixture executor failure")

    monkeypatch.setattr(lane, "SystemExecutor", FailedExecutor)
    manifest = run_with_private_config(
        config_path, source_archive, tmp_path / "runner-exception.json"
    )

    assert manifest["reasonCode"] == "RUNNER_EXCEPTION"
    assert manifest["clientIdentity"] == {
        "ripdpiSourceSha": "d" * 40,
        "artifactSha256": "e" * 64,
    }


def test_client_identity_descriptor_rejects_placeholder_digests(tmp_path: Path) -> None:
    config_path, _source_archive = write_private_runner_config(tmp_path)
    descriptor = config_path.parent / lane.CLIENT_IDENTITY_DESCRIPTOR_NAME
    descriptor.write_text(
        json.dumps(
            {
                "version": lane.CLIENT_IDENTITY_VERSION,
                "ripdpiSourceSha": "0" * 40,
                "artifactSha256": "e" * 64,
            }
        )
    )
    descriptor.chmod(0o600)

    with pytest.raises(ValueError, match="must bind a real artifact"):
        lane.load_config(config_path)


def run_with_private_config(
    config_path: Path, source_archive: Path, output: Path
) -> dict:
    assert (
        lane.main(
            [
                "run",
                "--config",
                str(config_path),
                "--output",
                str(output),
                "--source-sha",
                "1" * 40,
                "--workflow-run-id",
                "42",
                "--workflow-run-attempt",
                "1",
                "--source-archive",
                str(source_archive),
            ]
        )
        == 1
    )
    return json.loads(output.read_text())


def test_pass_requires_tcp_udp_restart_reload_and_nat_deltas() -> None:
    executor = FakeExecutor()
    manifest = lane.run_lane(config(), executor, metadata(), now=lambda: 2_000_000_000)

    assert manifest["classification"] == "PASS"
    assert manifest["reasonCode"] == "NONE"
    assert [phase["id"] for phase in manifest["phases"]] == [
        "direct_control",
        "initial_connect",
        "restart_recovery",
        "old_key_rejection",
        "reload_rotation_recovery",
    ]
    assert manifest["captureDigests"] == ["1" * 64, "2" * 64, "3" * 64]
    assert all(manifest["cleanup"].values())
    assert manifest["rotation"] == {
        "prepared": True,
        "oldKeyRejected": True,
        "newKeyMatched": True,
        "committed": True,
        "rolledBack": False,
    }
    assert "server_action:restart" in executor.calls
    assert "probe_once:old_key_rejection" in executor.calls
    assert "finalize_rotation:commit" in executor.calls
    assert executor.calls[-1] == "close"
    lane.validate_manifest(manifest, expected_source_sha="1" * 40, now=2_000_000_000)


def test_direct_control_failure_is_infrastructure_unavailable() -> None:
    executor = FakeExecutor(direct_ok=False)
    manifest = lane.run_lane(config(), executor, metadata(), now=lambda: 2_000_000_000)

    assert manifest["classification"] == "INFRA_UNAVAILABLE"
    assert manifest["reasonCode"] == "ECHO_CONTROL_UNAVAILABLE"
    assert executor.calls == [
        "deploy_source",
        "client_evidence:false",
        "direct_probe",
        "close",
    ]


def test_awg_roundtrip_failure_is_product_failure_and_cleans_up() -> None:
    executor = FakeExecutor(fail_phase="restart_recovery")
    manifest = lane.run_lane(config(), executor, metadata(), now=lambda: 2_000_000_000)

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "AWG_ROUNDTRIP_FAILED"
    assert executor.calls[-1] == "close"
    assert manifest["captureDigests"] == ["1" * 64]


def test_pass_cannot_omit_a_phase_or_capture() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    partial = copy.deepcopy(manifest)
    partial["phases"].pop()
    partial["captureDigests"].pop()

    try:
        lane.validate_manifest(partial, expected_source_sha="1" * 40, now=2_000_000_000)
    except ValueError as exc:
        assert "complete phase sequence" in str(exc)
    else:
        raise AssertionError("partial PASS manifest was accepted")


def test_stale_manifest_is_rejected() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    try:
        lane.validate_manifest(
            manifest,
            expected_source_sha="1" * 40,
            now=2_000_010_000,
            max_age_seconds=300,
        )
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale manifest was accepted")


def test_manifest_client_identity_is_bound_to_expected_artifact() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    lane.validate_manifest(
        manifest,
        expected_source_sha="1" * 40,
        expected_client_source_sha="d" * 40,
        expected_client_artifact_sha256="e" * 64,
        now=2_000_000_000,
    )
    manifest["clientIdentity"]["artifactSha256"] = "f" * 64
    with pytest.raises(ValueError, match="client artifact SHA mismatch"):
        lane.validate_manifest(
            manifest,
            expected_source_sha="1" * 40,
            expected_client_source_sha="d" * 40,
            expected_client_artifact_sha256="e" * 64,
            now=2_000_000_000,
        )


def test_optional_workflow_is_manual_fail_closed_and_uploads_evidence() -> None:
    workflow = (REPO_ROOT / ".github/workflows/real-vps-awg-nat.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "self-hosted" in workflow and "ripdpi-awg-vps" in workflow
    assert "skip" not in workflow.lower()
    assert "if: always()" in workflow
    assert "real-vps-awg-nat.py" in workflow
    assert "git archive --format=tar" in workflow
    assert "--source-archive" in workflow
    assert "--expected-source-archive-sha256" in workflow
    assert "--executor github_actions" in workflow
    assert "--expected-executor github_actions" in workflow
    assert "Remove private source archive" in workflow


def test_provenance_is_executor_neutral_and_binds_entrypoint() -> None:
    local_metadata = {
        **metadata(),
        "executor": "local_systemd",
        "entrypointPath": lane.LOCAL_ENTRYPOINT_PATH,
        "invocationId": "0123456789abcdef",
    }
    manifest = lane.run_lane(
        config(), FakeExecutor(), local_metadata, now=lambda: 2_000_000_000
    )

    lane.validate_manifest(
        manifest,
        expected_source_sha="1" * 40,
        expected_executor="local_systemd",
        expected_invocation_id="0123456789abcdef",
        expected_invocation_attempt=1,
        now=2_000_000_000,
    )
    assert manifest["provenance"] == {
        "executor": "local_systemd",
        "entrypointPath": lane.LOCAL_ENTRYPOINT_PATH,
        "invocationId": "0123456789abcdef",
        "invocationAttempt": 1,
        "sourceArchiveSha256": "2" * 64,
    }


def test_provenance_rejects_executor_entrypoint_substitution() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    manifest["provenance"]["entrypointPath"] = lane.LOCAL_ENTRYPOINT_PATH

    try:
        lane.validate_manifest(
            manifest, expected_source_sha="1" * 40, now=2_000_000_000
        )
    except ValueError as exc:
        assert "entrypoint mismatch" in str(exc)
    else:
        raise AssertionError("executor entrypoint substitution was accepted")


def test_legacy_workflow_flags_map_to_github_executor(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar"
    archive.write_bytes(b"exact source archive")
    manifest_path = tmp_path / "manifest.json"

    status = lane.main(
        [
            "run",
            "--config",
            str(tmp_path / "missing-runner.json"),
            "--output",
            str(manifest_path),
            "--source-sha",
            "1" * 40,
            "--source-archive",
            str(archive),
            "--workflow-run-id",
            "42",
            "--workflow-run-attempt",
            "3",
        ]
    )

    assert status == 1
    manifest = json.loads(manifest_path.read_text())
    assert manifest["provenance"]["executor"] == "github_actions"
    assert manifest["provenance"]["entrypointPath"] == lane.WORKFLOW_PATH
    assert manifest["provenance"]["invocationId"] == "42"
    assert manifest["provenance"]["invocationAttempt"] == 3
    common_validate = [
        "validate",
        "--manifest",
        str(manifest_path),
        "--expected-source-sha",
        "1" * 40,
        "--expected-source-archive-sha256",
        lane.sha256_bytes(archive.read_bytes()),
    ]
    assert lane.main(common_validate) == 1
    assert lane.main([*common_validate, "--allow-non-pass"]) == 0


def test_local_launcher_archives_exact_sha_and_validates_before_publish() -> None:
    launcher = (REPO_ROOT / "scripts" / "run-real-vps-awg-nat-local.sh").read_text()

    assert 'git -C "$REPO_ROOT" archive --format=tar "$source_sha"' in launcher
    assert 'git -C "$REPO_ROOT" diff-index --quiet HEAD' in launcher
    assert "--executor local_systemd" in launcher
    assert "--expected-executor local_systemd" in launcher
    assert 'CONFIG="/etc/ripdpi/real-vps-awg-nat-local.json"' in launcher
    assert "accepts no arguments" in launcher
    assert 'cmp -s "$RUNNER"' in launcher
    for installed_path in (
        "/etc/systemd/system/ripdpi-real-vps-awg-nat.service",
        "/etc/systemd/system/ripdpi-real-vps-awg-nat.timer",
        "/usr/lib/tmpfiles.d/ripdpi-real-vps-awg-nat.conf",
    ):
        assert f"cmp -s {installed_path}" in launcher
    assert "latest.json" in launcher
    assert launcher.index('rm -f -- "$evidence_dir/latest.json"') < launcher.index(
        '"$RUNNER" run'
    )
    assert "--allow-non-pass" in launcher
    assert 'quarantine="$quarantine_dir/invalid-' in launcher
    assert "run_status == 0 && validate_status == 0" in launcher
    assert "GITHUB_" not in launcher


def test_preflight_failures_are_redacted_nonpass_evidence_without_latest_mutation() -> (
    None
):
    manifest = lane.failure_manifest(metadata(), "4" * 64, "PREFLIGHT_CONFIG_INVALID")
    lane.validate_manifest(
        manifest,
        expected_source_sha="1" * 40,
        now=manifest["generatedAtEpoch"],
    )

    launcher = (REPO_ROOT / "scripts" / "run-real-vps-awg-nat-local.sh").read_text()
    assert "emit_preflight_failure" in launcher
    assert "preflight_fail()" in launcher
    for category in (
        "PREFLIGHT_TOOL_MISSING",
        "PREFLIGHT_LOCK_BUSY",
        "PREFLIGHT_CONFIG_INVALID",
        "PREFLIGHT_RUNNER_INVALID",
        "PREFLIGHT_SOURCE_UNSAFE",
        "PREFLIGHT_SOURCE_MISMATCH",
    ):
        assert category in launcher
    assert launcher.index('rm -f -- "$evidence_dir/latest.json"') > launcher.index(
        'git -C "$REPO_ROOT" diff-index --quiet HEAD'
    )
    assert "preflight_fail PREFLIGHT_LOCK_BUSY" in launcher
    assert "preflight_fail PREFLIGHT_CONFIG_INVALID" in launcher
    assert "preflight_fail PREFLIGHT_RUNNER_INVALID" in launcher
    assert "preflight_fail PREFLIGHT_SOURCE_UNSAFE" in launcher


def test_missing_readlink_emits_preflight_evidence(tmp_path: Path) -> None:
    launcher = REPO_ROOT / "scripts/run-real-vps-awg-nat-local.sh"
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    for name in (
        "awk",
        "chmod",
        "cmp",
        "date",
        "find",
        "flock",
        "git",
        "install",
        "mkdir",
        "mv",
        "python3",
        "rm",
        "sha256sum",
        "stat",
    ):
        resolved = shutil.which(name)
        if resolved is None:
            assert name == "flock"
            (tool_dir / name).write_text("#!/bin/sh\nexit 0\n")
            (tool_dir / name).chmod(0o755)
        else:
            (tool_dir / name).symlink_to(resolved)
    state = tmp_path / "state"
    runtime = tmp_path / "runtime"
    state.mkdir()
    runtime.mkdir()

    completed = subprocess.run(
        ["/bin/bash", str(launcher)],
        env={
            "PATH": str(tool_dir),
            "RUNTIME_DIRECTORY": str(runtime),
            "STATE_DIRECTORY": str(state),
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 75
    records = list((state / "evidence").glob("preflight-*.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text())["reasonCode"] == "PREFLIGHT_TOOL_MISSING"


def test_unresolvable_repo_root_emits_source_unsafe_evidence(tmp_path: Path) -> None:
    launcher = REPO_ROOT / "scripts/run-real-vps-awg-nat-local.sh"
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    for name in (
        "awk",
        "chmod",
        "cmp",
        "date",
        "find",
        "flock",
        "git",
        "install",
        "mkdir",
        "mv",
        "python3",
        "rm",
        "sha256sum",
        "stat",
    ):
        resolved = shutil.which(name)
        if resolved is None:
            assert name == "flock"
            (tool_dir / name).write_text("#!/bin/sh\nexit 0\n")
            (tool_dir / name).chmod(0o755)
        else:
            (tool_dir / name).symlink_to(resolved)
    fake_readlink = tool_dir / "readlink"
    fake_readlink.write_text("#!/bin/sh\nexit 1\n")
    fake_readlink.chmod(0o755)
    state = tmp_path / "state"
    runtime = tmp_path / "runtime"
    state.mkdir()
    runtime.mkdir()

    completed = subprocess.run(
        ["/bin/bash", str(launcher)],
        env={
            "PATH": str(tool_dir),
            "RUNTIME_DIRECTORY": str(runtime),
            "STATE_DIRECTORY": str(state),
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 75
    records = list((state / "evidence").glob("preflight-*.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text())["reasonCode"] == "PREFLIGHT_SOURCE_UNSAFE"


def test_preflight_emitter_writes_canonical_redacted_manifest_without_latest_update(
    tmp_path: Path,
) -> None:
    launcher = (REPO_ROOT / "scripts" / "run-real-vps-awg-nat-local.sh").read_text()
    match = re.search(
        r"emit_preflight_failure\(\) \{.*?\n\}\n\npreflight_fail", launcher, re.DOTALL
    )
    assert match is not None
    emitter = match.group(0).removesuffix("\n\npreflight_fail")
    evidence_dir = tmp_path / "evidence"
    harness = f"""
set -euo pipefail
evidence_dir={shlex.quote(str(evidence_dir))}
quarantine_dir={shlex.quote(str(tmp_path / "quarantine"))}
preflight_epoch=2000000000
mkdir -p "$evidence_dir"
printf prior > "$evidence_dir/latest.json"
{emitter}
emit_preflight_failure PREFLIGHT_CONFIG_INVALID
"""
    completed = subprocess.run(["bash", "-c", harness], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert (evidence_dir / "latest.json").read_text() == "prior"
    records = list(evidence_dir.glob("preflight-*.json"))
    assert len(records) == 1
    raw = records[0].read_bytes()
    manifest = json.loads(raw)
    assert raw == lane.canonical_json_bytes(manifest)
    lane.validate_manifest(
        manifest,
        expected_source_sha="0" * 40,
        now=2_000_000_000,
    )
    assert manifest["classification"] == "INFRA_UNAVAILABLE"
    assert manifest["reasonCode"] == "PREFLIGHT_CONFIG_INVALID"
    assert manifest["clientIdentity"] == {
        "ripdpiSourceSha": "0" * 40,
        "artifactSha256": "0" * 64,
    }


def test_local_installer_pins_root_owned_source_and_fixed_units() -> None:
    installer = (
        REPO_ROOT / "scripts" / "install-real-vps-awg-nat-local.sh"
    ).read_text()
    service = (
        REPO_ROOT / "scripts/systemd/ripdpi-real-vps-awg-nat.service"
    ).read_text()
    timer = (REPO_ROOT / "scripts/systemd/ripdpi-real-vps-awg-nat.timer").read_text()
    tmpfiles = (
        REPO_ROOT / "scripts/tmpfiles.d/ripdpi-real-vps-awg-nat.conf"
    ).read_text()

    assert "git clone --quiet --no-hardlinks --no-checkout" in installer
    assert 'checkout --quiet --detach "$source_sha"' in installer
    assert "remote remove origin" in installer
    assert "root-owned mode 0600" in installer
    assert 'LOCK_DIR="/run/lock/ripdpi-real-vps-awg-nat"' in installer
    assert "flock -n 9" in installer
    assert "/var/lib/ripdpi-real-vps-awg-nat/evidence/latest.json" in installer
    assert "validate_root_hook" in installer
    assert "/usr/local/libexec/ripdpi-real-vps-awg-nat-hooks" in installer
    assert 'value["serverControlHook"] = control' in installer
    assert "/etc/ripdpi/real-vps-awg-nat-local.json" in installer
    assert "systemd-analyze verify" in installer
    assert "systemctl enable --now ripdpi-real-vps-awg-nat.timer" in installer
    assert "systemd-tmpfiles --create ripdpi-real-vps-awg-nat.conf" in installer
    assert "ExecStart=/usr/local/libexec/ripdpi-real-vps-awg-nat-local" in service
    assert "ExecStart=" in service and " %" not in service
    for directive in (
        "RuntimeDirectoryMode=0700",
        "StateDirectoryMode=0700",
        "UMask=0077",
        "PrivateTmp=true",
        "NoNewPrivileges=true",
        "CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_ADMIN",
        "ProtectSystem=strict",
        "DeviceAllow=/dev/net/tun rw",
        "/run/netns",
        "/run/wireguard",
    ):
        assert directive in service
    assert "d /run/netns 0755 root root -" in tmpfiles
    assert "d /run/wireguard 0755 root root -" in tmpfiles
    assert "d /run/lock/ripdpi-real-vps-awg-nat 0700 root root -" in tmpfiles
    assert "OnCalendar=Tue *-*-* 05:23:00 UTC" in timer
    assert "Persistent=true" in timer


def test_private_path_rejects_writable_parent_chain(tmp_path: Path) -> None:
    unsafe_parent = tmp_path / "unsafe"
    unsafe_parent.mkdir(mode=0o777)
    unsafe_parent.chmod(0o777)
    hook = unsafe_parent / "hook"
    hook.write_text("#!/bin/sh\n")
    hook.chmod(0o700)

    try:
        lane._secure_path(str(hook), executable=True)
    except ValueError as exc:
        assert "parent has unsafe owner or mode" in str(exc)
    else:
        raise AssertionError("private hook below writable parent was accepted")


def test_private_path_executes_resolved_target_not_mutable_parent_symlink(
    tmp_path: Path,
) -> None:
    secure_parent = tmp_path / "secure"
    secure_parent.mkdir(mode=0o700)
    hook = secure_parent / "hook"
    hook.write_text("#!/bin/sh\n")
    hook.chmod(0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(secure_parent, target_is_directory=True)

    resolved = lane._secure_path(str(alias / "hook"), executable=True)

    assert resolved == hook.resolve()


def test_capture_stays_within_bounded_root_capability_set() -> None:
    source = SCRIPT.read_text()
    assert '"tcpdump",\n                "-Z",\n                "root",' in source


def test_firewall_nat_rule_has_stable_counter_comment() -> None:
    vars_ = merge_render_vars()
    vars_["vpn"] = {**vars_["vpn"], "enable_amneziawg": True}
    vars_["amneziawg_secrets"] = {
        "instances": [{"name": "awg-primary"}, {"name": "awg-backup"}]
    }

    rendered = render_template(FIREWALL_TEMPLATE, vars_)

    for interface in ("awg-primary", "awg-backup"):
        rule = (
            f'iifname "{interface}" oifname != "{interface}" '
            f'counter masquerade comment "awg-nat-{interface}"'
        )
        assert rendered.count(rule) == 1
    assert 'comment "awg-nat-awg0"' not in rendered
    assert 'counter comment "awg-nat-' not in rendered


def test_manifest_serialization_is_deterministic() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    first = lane.canonical_json_bytes(manifest)
    second = lane.canonical_json_bytes(json.loads(first))
    assert first == second


def test_private_config_accepts_same_server_peer_and_hashes_owned_producers(
    tmp_path: Path,
) -> None:
    config_path, _source_archive = write_private_runner_config(tmp_path)

    loaded = lane.load_config(config_path)

    assert loaded["runnerIdSha256"] != "a" * 64
    assert loaded["serverControlHookSha256"] == lane.sha256_bytes(b"private\n")
    assert loaded["serverDeployHookSha256"] == lane.sha256_bytes(b"private\n")
    assert loaded["rotationHookSha256"] == lane.sha256_bytes(b"private\n")
    assert os.path.isabs(loaded["clientConfigPath"])


def test_missing_client_configs_are_missing_credentials(tmp_path: Path) -> None:
    for label, omitted in (("current", "current"), ("rotated", "rotated")):
        case_path = tmp_path / label
        case_path.mkdir()
        config_path, source_archive = write_private_runner_config(
            case_path,
            omit_current=omitted == "current",
            omit_rotated=omitted == "rotated",
        )

        manifest = run_with_private_config(
            config_path, source_archive, case_path / "manifest.json"
        )

        assert (manifest["classification"], manifest["reasonCode"]) == (
            "INFRA_UNAVAILABLE",
            "MISSING_CREDENTIALS",
        )


def test_incomplete_or_duplicate_client_keys_are_missing_credentials(
    tmp_path: Path,
) -> None:
    incomplete = "\n".join(("[Interface]", f"PrivateKey = {'A' * 43}=", "[Peer]", ""))
    duplicate = "\n".join(
        (
            "[Interface]",
            f"PrivateKey = {'A' * 43}=",
            "PrivateKey = malformed",
            "[Peer]",
            f"PublicKey = {'D' * 43}=",
            f"PresharedKey = {'B' * 43}=",
            "",
        )
    )
    duplicate_psk = "\n".join(
        (
            "[Interface]",
            f"PrivateKey = {'A' * 43}=",
            "[Peer]",
            f"PublicKey = {'D' * 43}=",
            f"PresharedKey = {'B' * 43}=",
            "PresharedKey = malformed",
            "",
        )
    )
    for label, contents in (
        ("incomplete", incomplete),
        ("duplicate-private", duplicate),
        ("duplicate-psk", duplicate_psk),
    ):
        case_path = tmp_path / label
        case_path.mkdir()
        config_path, source_archive = write_private_runner_config(
            case_path, rotated_contents=contents
        )

        manifest = run_with_private_config(
            config_path, source_archive, case_path / "manifest.json"
        )

        assert (manifest["classification"], manifest["reasonCode"]) == (
            "INFRA_UNAVAILABLE",
            "MISSING_CREDENTIALS",
        )


@pytest.mark.parametrize(
    ("label", "rotated_contents"),
    (
        (
            "reused-private",
            "\n".join(
                (
                    "[Interface]",
                    f"PrivateKey = {'A' * 43}=",
                    "[Peer]",
                    f"PublicKey = {'B' * 43}=",
                    f"PresharedKey = {'E' * 43}=",
                    "",
                )
            ),
        ),
        (
            "changed-server-peer",
            "\n".join(
                (
                    "[Interface]",
                    f"PrivateKey = {'C' * 43}=",
                    "[Peer]",
                    f"PublicKey = {'D' * 43}=",
                    f"PresharedKey = {'E' * 43}=",
                    "",
                )
            ),
        ),
        (
            "reused-psk",
            "\n".join(
                (
                    "[Interface]",
                    f"PrivateKey = {'C' * 43}=",
                    "[Peer]",
                    f"PublicKey = {'B' * 43}=",
                    f"PresharedKey = {'B' * 43}=",
                    "",
                )
            ),
        ),
    ),
)
def test_rotated_client_rejects_invalid_rotation_key_relationships(
    tmp_path: Path, label: str, rotated_contents: str
) -> None:
    config_path, source_archive = write_private_runner_config(
        tmp_path, rotated_contents=rotated_contents
    )

    manifest = run_with_private_config(
        config_path, source_archive, tmp_path / f"{label}.json"
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "CONFIG_INVALID",
    )


def test_dangling_client_symlink_remains_config_invalid(tmp_path: Path) -> None:
    config_path, source_archive = write_private_runner_config(tmp_path)
    contract = json.loads(config_path.read_text())
    current = Path(contract["clientConfigPath"])
    current.unlink()
    current.symlink_to(tmp_path / "missing-target.conf")

    manifest = run_with_private_config(
        config_path, source_archive, tmp_path / "manifest.json"
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "CONFIG_INVALID",
    )


def test_malformed_runner_json_remains_config_invalid(tmp_path: Path) -> None:
    config_path = tmp_path / "runner.json"
    config_path.write_text("{not-json")
    config_path.chmod(0o600)
    source_archive = tmp_path / "source.tar"
    source_archive.write_bytes(b"source")

    manifest = run_with_private_config(
        config_path, source_archive, tmp_path / "manifest.json"
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "CONFIG_INVALID",
    )


def test_missing_hooks_remain_config_invalid(tmp_path: Path) -> None:
    for field in ("serverControlHook", "serverDeployHook", "rotationHook"):
        case_path = tmp_path / field
        case_path.mkdir()
        config_path, source_archive = write_private_runner_config(case_path)
        contract = json.loads(config_path.read_text())
        Path(contract[field]).unlink()

        manifest = run_with_private_config(
            config_path, source_archive, case_path / "manifest.json"
        )

        assert (manifest["classification"], manifest["reasonCode"]) == (
            "INFRA_UNAVAILABLE",
            "CONFIG_INVALID",
        )


def test_runtime_missing_credentials_keep_distinct_classification() -> None:
    class MissingCurrent(FakeExecutor):
        def client_evidence(self, *, rotated: bool) -> dict:
            if not rotated:
                raise lane.MissingCredentials("current config disappeared")
            return super().client_evidence(rotated=rotated)

    class MissingRotated(FakeExecutor):
        def client_evidence(self, *, rotated: bool) -> dict:
            if rotated:
                raise lane.MissingCredentials("rotation produced no credentials")
            return super().client_evidence(rotated=rotated)

    current = lane.run_lane(
        config(), MissingCurrent(), metadata(), now=lambda: 2_000_000_000
    )
    rotated = lane.run_lane(
        config(), MissingRotated(), metadata(), now=lambda: 2_000_000_000
    )

    assert (current["classification"], current["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "MISSING_CREDENTIALS",
    )
    assert (rotated["classification"], rotated["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "MISSING_CREDENTIALS",
    )
    assert rotated["rotation"]["rolledBack"] is True


def test_post_commit_missing_credentials_roll_back_with_distinct_reason() -> None:
    class MissingAfterCommit(FakeExecutor):
        def __init__(self):
            super().__init__()
            self.current_evidence_reads = 0

        def client_evidence(self, *, rotated: bool) -> dict:
            if not rotated:
                self.current_evidence_reads += 1
                if self.current_evidence_reads == 2:
                    raise lane.MissingCredentials("promoted config disappeared")
            return super().client_evidence(rotated=rotated)

        def finalize_rotation(self, action: str) -> dict:
            if action == "commit":
                self.calls.append("finalize_rotation:commit")
                return {
                    "action": action,
                    "configGenerationSha256": self.next_generation,
                    "peerConfigSha256": self.next_peer,
                    "currentClientConfigSha256": self.rotated_client[
                        "clientConfigSha256"
                    ],
                }
            return super().finalize_rotation(action)

    manifest = lane.run_lane(
        config(), MissingAfterCommit(), metadata(), now=lambda: 2_000_000_000
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "MISSING_CREDENTIALS",
    )
    assert manifest["rotation"]["rolledBack"] is True


def test_nonpass_manifest_still_validates_but_cannot_be_green() -> None:
    manifest = lane.failure_manifest(metadata(), "4" * 64, "PREREQUISITE_MISSING")
    lane.validate_manifest(manifest, expected_source_sha="1" * 40)
    assert manifest["classification"] == "INFRA_UNAVAILABLE"


def test_restart_noop_cannot_pass() -> None:
    class NoRestartExecutor(FakeExecutor):
        def server_action(self, action: str) -> None:
            self.calls.append(f"server_action:{action}")
            if action == "reload":
                super().server_action(action)

    manifest = lane.run_lane(
        config(), NoRestartExecutor(), metadata(), now=lambda: 2_000_000_000
    )

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "RESTART_NOT_OBSERVED"


def test_reload_noop_cannot_pass_and_rolls_back() -> None:
    class NoReloadExecutor(FakeExecutor):
        def server_action(self, action: str) -> None:
            self.calls.append(f"server_action:{action}")
            if action == "restart":
                self.service_generation = "d" * 64

    executor = NoReloadExecutor()
    manifest = lane.run_lane(config(), executor, metadata(), now=lambda: 2_000_000_000)

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "RELOAD_NOT_OBSERVED"
    assert manifest["rotation"]["rolledBack"] is True
    assert "finalize_rotation:rollback" in executor.calls


def test_old_key_negative_control_cannot_be_noop() -> None:
    class OldKeyAcceptedExecutor(FakeExecutor):
        def probe_once(self, phase: str) -> dict:
            self.calls.append(f"probe_once:{phase}")
            self.latest_handshake += 1
            self.peer_rx += 10
            self.peer_tx += 11
            self.nat_packets += 2
            self.nat_bytes += 200
            return self._probe(True)

    manifest = lane.run_lane(
        config(), OldKeyAcceptedExecutor(), metadata(), now=lambda: 2_000_000_000
    )

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "OLD_KEY_STILL_ACCEPTED"
    assert manifest["rotation"]["rolledBack"] is True


@pytest.mark.parametrize(("tcp_ok", "udp_ok"), [(True, False), (False, True)])
def test_old_key_partial_acceptance_is_product_failure(
    tcp_ok: bool, udp_ok: bool
) -> None:
    class PartiallyAcceptedOldKeyExecutor(FakeExecutor):
        def probe_once(self, phase: str) -> dict:
            self.calls.append(f"probe_once:{phase}")
            return {
                "tcp": {"ok": tcp_ok, "durationMs": 8 if tcp_ok else None},
                "udp": {"ok": udp_ok, "durationMs": 6 if udp_ok else None},
            }

    manifest = lane.run_lane(
        config(),
        PartiallyAcceptedOldKeyExecutor(),
        metadata(),
        now=lambda: 2_000_000_000,
    )

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "OLD_KEY_STILL_ACCEPTED"
    assert manifest["rotation"]["rolledBack"] is True


@pytest.mark.parametrize(("tcp_ok", "udp_ok"), [(True, False), (False, True)])
def test_pass_manifest_rejects_partial_old_key_acceptance(
    tcp_ok: bool, udp_ok: bool
) -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    old_key_phase = next(
        phase for phase in manifest["phases"] if phase["id"] == "old_key_rejection"
    )
    old_key_phase["tcp"] = {
        "ok": tcp_ok,
        "durationMs": 8 if tcp_ok else None,
    }
    old_key_phase["udp"] = {
        "ok": udp_ok,
        "durationMs": 6 if udp_ok else None,
    }

    with pytest.raises(ValueError, match="accepted the old key"):
        lane.validate_manifest(
            manifest, expected_source_sha="1" * 40, now=2_000_000_000
        )


def test_failure_after_reload_restores_previous_server_and_client() -> None:
    executor = FakeExecutor(fail_phase="reload_rotation_recovery")
    manifest = lane.run_lane(config(), executor, metadata(), now=lambda: 2_000_000_000)

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "AWG_ROUNDTRIP_FAILED"
    assert manifest["rotation"]["rolledBack"] is True
    assert executor.current_peer == "9" * 64
    assert executor.current_client["peerConfigSha256"] == "9" * 64
    assert all(manifest["cleanup"].values())


def test_close_failure_is_visible_in_manifest() -> None:
    class CloseFailureExecutor(FakeExecutor):
        def close(self) -> None:
            self.calls.append("close")
            raise RuntimeError("scratch remains")

    manifest = lane.run_lane(
        config(), CloseFailureExecutor(), metadata(), now=lambda: 2_000_000_000
    )

    assert manifest["classification"] == "INFRA_UNAVAILABLE"
    assert manifest["reasonCode"] == "CLEANUP_FAILED"
    assert manifest["cleanup"]["scratchRemoved"] is False


def test_pass_phase_outcomes_are_fixed_by_phase_id() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    tampered = copy.deepcopy(manifest)
    tampered["phases"][0]["expected"] = "failure"
    tampered["phases"][0]["tcp"] = {"ok": False, "durationMs": None}
    tampered["phases"][0]["udp"] = {"ok": False, "durationMs": None}

    try:
        lane.validate_manifest(
            tampered, expected_source_sha="1" * 40, now=2_000_000_000
        )
    except ValueError as exc:
        assert "phase outcome contract" in str(exc)
    else:
        raise AssertionError("failed direct control was accepted as PASS")


def test_manifest_archive_digest_is_bound_to_workflow_value() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )

    try:
        lane.validate_manifest(
            manifest,
            expected_source_sha="1" * 40,
            expected_source_archive_sha256="f" * 64,
            now=2_000_000_000,
        )
    except ValueError as exc:
        assert "source archive SHA mismatch" in str(exc)
    else:
        raise AssertionError("mismatched source archive digest was accepted")


def test_cleanup_retains_handles_until_orphan_verification_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    executor = object.__new__(lane.SystemExecutor)
    executor.scratch = tmp_path / "scratch"
    executor.scratch.mkdir()
    executor.namespace = "awgleak"
    executor.interface = "awgleak0"
    executor.namespace_created = True
    executor.interface_created = True
    executor.go_process = None
    executor.capture_process = None
    executor.capture_path = executor.scratch / "capture.pcap"
    executor.capture_path.write_bytes(b"x" * 25)
    leaked = True

    def fake_run(command, **_kwargs):
        nonlocal leaked
        stdout = "awgleak\n" if command == ["ip", "netns", "list"] and leaked else ""
        returncode = 1 if command[:4] == ["ip", "link", "show", "awgleak0"] else 0
        return lane.subprocess.CompletedProcess(command, returncode, stdout=stdout)

    monkeypatch.setattr(lane.subprocess, "run", fake_run)

    try:
        executor._cleanup_client(require_capture=True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("leaked namespace was accepted as cleaned")
    assert executor.namespace == "awgleak"
    assert executor.interface == "awgleak0"

    leaked = False
    executor.close()

    assert executor.namespace is None
    assert executor.interface is None
    assert not executor.scratch.exists()


def test_cleanup_never_deletes_unowned_namespace_or_interface(
    tmp_path: Path, monkeypatch
) -> None:
    executor = object.__new__(lane.SystemExecutor)
    executor.scratch = tmp_path / "scratch"
    executor.scratch.mkdir()
    executor.namespace = "preexisting"
    executor.interface = "preexisting0"
    executor.namespace_created = False
    executor.interface_created = False
    executor.go_process = None
    executor.capture_process = None
    executor.capture_path = None
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return lane.subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr(lane.subprocess, "run", fake_run)

    executor._cleanup_client(require_capture=False)

    assert not any("delete" in command for command in commands)
    assert executor.namespace is None
    assert executor.interface is None


def test_deploy_outage_and_product_failure_are_distinct() -> None:
    class DeployOutage(FakeExecutor):
        def deploy_source(self, source_sha: str, archive_sha256: str) -> dict:
            raise lane.InfrastructureUnavailable("ssh unavailable")

    class DeployFailure(FakeExecutor):
        def deploy_source(self, source_sha: str, archive_sha256: str) -> dict:
            raise RuntimeError("ansible rejected current source")

    outage = lane.run_lane(
        config(), DeployOutage(), metadata(), now=lambda: 2_000_000_000
    )
    failure = lane.run_lane(
        config(), DeployFailure(), metadata(), now=lambda: 2_000_000_000
    )

    assert (outage["classification"], outage["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "DEPLOY_UNAVAILABLE",
    )
    assert (failure["classification"], failure["reasonCode"]) == (
        "PRODUCT_FAILURE",
        "DEPLOY_FAILED",
    )


def test_hook_exit_taxonomy_distinguishes_product_from_infrastructure(
    monkeypatch,
) -> None:
    def fail_with(returncode: int) -> None:
        def fake_run(_command, **_kwargs):
            raise lane.subprocess.CalledProcessError(returncode, ["hook"])

        monkeypatch.setattr(lane.SystemExecutor, "_run", staticmethod(fake_run))

    fail_with(70)
    try:
        lane.SystemExecutor._run_hook(["hook"])
    except lane.HookProductFailure:
        pass
    else:
        raise AssertionError("hook exit 70 was not classified as a product failure")

    fail_with(75)
    try:
        lane.SystemExecutor._run_hook(["hook"])
    except lane.InfrastructureUnavailable:
        pass
    else:
        raise AssertionError("hook exit 75 was not classified as infrastructure")


def test_malformed_status_is_product_failure() -> None:
    class MalformedStatus(FakeExecutor):
        def server_status(self) -> dict:
            raise ValueError("malformed status")

    manifest = lane.run_lane(
        config(), MalformedStatus(), metadata(), now=lambda: 2_000_000_000
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "PRODUCT_FAILURE",
        "SERVER_CONTROL_UNAVAILABLE",
    )


def test_status_outage_remains_infrastructure_unavailable() -> None:
    class StatusOutage(FakeExecutor):
        def server_status(self) -> dict:
            raise lane.InfrastructureUnavailable("status transport unavailable")

    manifest = lane.run_lane(
        config(), StatusOutage(), metadata(), now=lambda: 2_000_000_000
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "SERVER_CONTROL_UNAVAILABLE",
    )


def test_server_action_preserves_hook_failure_taxonomy() -> None:
    class ActionFailure(FakeExecutor):
        def __init__(self, error: Exception):
            super().__init__()
            self.error = error

        def server_action(self, action: str) -> None:
            if action == "restart":
                self.calls.append("server_action:restart")
                raise self.error
            super().server_action(action)

    product = lane.run_lane(
        config(),
        ActionFailure(lane.HookProductFailure("restart rejected")),
        metadata(),
        now=lambda: 2_000_000_000,
    )
    infrastructure = lane.run_lane(
        config(),
        ActionFailure(lane.InfrastructureUnavailable("restart unavailable")),
        metadata(),
        now=lambda: 2_000_000_000,
    )

    assert (product["classification"], product["reasonCode"]) == (
        "PRODUCT_FAILURE",
        "RESTART_FAILED",
    )
    assert (infrastructure["classification"], infrastructure["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "SERVER_CONTROL_UNAVAILABLE",
    )


def test_rotation_prepare_preserves_hook_failure_taxonomy() -> None:
    class PrepareFailure(FakeExecutor):
        def __init__(self, error: Exception):
            super().__init__()
            self.error = error

        def stage_rotation(self) -> dict:
            self.calls.append("stage_rotation")
            raise self.error

    product = lane.run_lane(
        config(),
        PrepareFailure(lane.HookProductFailure("prepare rejected")),
        metadata(),
        now=lambda: 2_000_000_000,
    )
    infrastructure = lane.run_lane(
        config(),
        PrepareFailure(lane.InfrastructureUnavailable("prepare unavailable")),
        metadata(),
        now=lambda: 2_000_000_000,
    )

    assert (product["classification"], product["reasonCode"]) == (
        "PRODUCT_FAILURE",
        "ROTATION_FAILED",
    )
    assert (infrastructure["classification"], infrastructure["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "SERVER_CONTROL_UNAVAILABLE",
    )
    assert product["rotation"]["rolledBack"] is True
    assert infrastructure["rotation"]["rolledBack"] is True


def test_malformed_commit_receipt_is_product_failure_and_rolls_back() -> None:
    class MalformedCommit(FakeExecutor):
        def finalize_rotation(self, action: str) -> dict:
            if action == "commit":
                self.calls.append("finalize_rotation:commit")
                return {
                    "action": "rollback",
                    "configGenerationSha256": self.next_generation,
                    "peerConfigSha256": self.next_peer,
                    "currentClientConfigSha256": self.rotated_client[
                        "clientConfigSha256"
                    ],
                }
            return super().finalize_rotation(action)

    manifest = lane.run_lane(
        config(), MalformedCommit(), metadata(), now=lambda: 2_000_000_000
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "PRODUCT_FAILURE",
        "COMMIT_FAILED",
    )
    assert manifest["rotation"]["rolledBack"] is True


def test_commit_outage_remains_infrastructure_unavailable_and_rolls_back() -> None:
    class CommitOutage(FakeExecutor):
        def finalize_rotation(self, action: str) -> dict:
            if action == "commit":
                self.calls.append("finalize_rotation:commit")
                raise lane.InfrastructureUnavailable("commit transport unavailable")
            return super().finalize_rotation(action)

    manifest = lane.run_lane(
        config(), CommitOutage(), metadata(), now=lambda: 2_000_000_000
    )

    assert (manifest["classification"], manifest["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "COMMIT_FAILED",
    )
    assert manifest["rotation"]["rolledBack"] is True


def test_rollback_failure_preserves_hook_failure_taxonomy() -> None:
    class RollbackFailure(FakeExecutor):
        def __init__(self, error: Exception):
            super().__init__(fail_phase="reload_rotation_recovery")
            self.error = error

        def finalize_rotation(self, action: str) -> dict:
            if action == "rollback":
                self.calls.append("finalize_rotation:rollback")
                raise self.error
            return super().finalize_rotation(action)

    product = lane.run_lane(
        config(),
        RollbackFailure(lane.HookProductFailure("rollback rejected")),
        metadata(),
        now=lambda: 2_000_000_000,
    )
    infrastructure = lane.run_lane(
        config(),
        RollbackFailure(lane.InfrastructureUnavailable("rollback unavailable")),
        metadata(),
        now=lambda: 2_000_000_000,
    )

    assert (product["classification"], product["reasonCode"]) == (
        "PRODUCT_FAILURE",
        "ROLLBACK_FAILED",
    )
    assert (infrastructure["classification"], infrastructure["reasonCode"]) == (
        "INFRA_UNAVAILABLE",
        "ROLLBACK_FAILED",
    )


def test_malformed_prepare_receipt_still_rolls_back_trusted_baseline() -> None:
    class MalformedPrepare(FakeExecutor):
        def stage_rotation(self) -> dict:
            receipt = super().stage_rotation()
            receipt["rotatedClientConfigSha256"] = "f" * 64
            return receipt

    executor = MalformedPrepare()
    manifest = lane.run_lane(config(), executor, metadata(), now=lambda: 2_000_000_000)

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "ROTATION_RECEIPT_INVALID"
    assert manifest["rotation"]["prepared"] is True
    assert manifest["rotation"]["rolledBack"] is True
    assert manifest["cleanup"]["serverTransactionFinalized"] is True
    assert "finalize_rotation:rollback" in executor.calls


def test_prepare_exception_uses_idempotent_rollback() -> None:
    class PrepareFailure(FakeExecutor):
        def stage_rotation(self) -> dict:
            self.calls.append("stage_rotation")
            raise RuntimeError("prepare failed after staging")

    executor = PrepareFailure()
    manifest = lane.run_lane(config(), executor, metadata(), now=lambda: 2_000_000_000)

    assert manifest["classification"] == "PRODUCT_FAILURE"
    assert manifest["reasonCode"] == "ROTATION_FAILED"
    assert manifest["rotation"]["prepared"] is True
    assert manifest["rotation"]["rolledBack"] is True
    assert "finalize_rotation:rollback" in executor.calls
