"""Contract tests for the recurring real-VPS AWG/NAT lane."""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import os
import re
import fcntl
import shutil
import shlex
import stat
import subprocess
import time
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.template_render import merge_render_vars, render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "real-vps-awg-nat.py"
FIREWALL_TEMPLATE = REPO_ROOT / "ansible/roles/firewall/templates/nftables.conf.j2"
CLIENT_ACCEPTANCE_NAME = "real-vps-awg-client-acceptance.json"


def load_module():
    spec = importlib.util.spec_from_file_location("real_vps_awg_nat", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


lane = load_module()


def live_client_acceptance(**overrides) -> dict:
    value = {
        "format": "ripdpi_awg_live_acceptance_v1",
        "ripdpiSourceSha": "d" * 40,
        "apkSha256": "e" * 64,
        "reportSha256": "f" * 64,
        "startedAtEpoch": 1_999_999_940,
        "finishedAtEpoch": 1_999_999_980,
        "transport": "amneziawg",
        "pass": True,
        "outcomes": {
            "routedTcp": True,
            "routedUdp": True,
            "recovery": True,
            "staleKeyRejected": True,
            "cleanup": True,
        },
    }
    value.update(overrides)
    correlation_payload = (
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    value["correlationSha256"] = hashlib.sha256(correlation_payload).hexdigest()
    return value


def signed_client_handoff(
    tmp_path: Path,
    acceptance: dict,
    *,
    nonce: str,
    invocation_id: str,
    invocation_attempt: int = 1,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    tmp_path.chmod(0o700)
    private_key = tmp_path / "client-signing-key.pem"
    public_key = tmp_path / "client-signing-key.pub.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", private_key],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            private_key,
            "-pubout",
            "-out",
            public_key,
        ],
        check=True,
        capture_output=True,
    )
    private_key.chmod(0o600)
    public_key.chmod(0o600)
    envelope = {
        "format": "ripdpi_awg_live_acceptance_handoff_v1",
        "invocationId": invocation_id,
        "invocationAttempt": invocation_attempt,
        "nonce": nonce,
        "signatureAlgorithm": "ed25519",
        "acceptance": acceptance,
    }
    payload_path = tmp_path / "payload.json"
    signature_path = tmp_path / "signature.bin"
    payload_path.write_bytes(lane.client_acceptance_signature_payload(envelope))
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-inkey",
            private_key,
            "-rawin",
            "-in",
            payload_path,
            "-out",
            signature_path,
        ],
        check=True,
        capture_output=True,
    )
    envelope["signatureBase64"] = base64.b64encode(signature_path.read_bytes()).decode(
        "ascii"
    )
    descriptor = tmp_path / f"{nonce}.json"
    descriptor.write_bytes(lane.canonical_json_bytes(envelope))
    descriptor.chmod(0o600)
    return descriptor, public_key


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
        self.deployed_source = "1" * 40
        self.deployed_archive = "2" * 64

    def _status(self) -> dict:
        return {
            "serviceActive": True,
            "interfaceUp": True,
            "deployedSourceSha": self.deployed_source,
            "deployedArchiveSha256": self.deployed_archive,
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
        self.deployed_source = source_sha
        self.deployed_archive = archive_sha256
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
        "engineIdentity": {
            "amneziawgGoCommit": "a" * 40,
            "amneziawgGoBinarySha256": "b" * 64,
        },
        "clientAcceptance": live_client_acceptance(),
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
    client_identity = tmp_path / CLIENT_ACCEPTANCE_NAME
    if include_client_identity:
        acceptance_now = int(time.time())
        client_identity.write_bytes(
            lane.canonical_json_bytes(
                live_client_acceptance(
                    startedAtEpoch=acceptance_now - 40,
                    finishedAtEpoch=acceptance_now - 10,
                )
            )
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


def test_private_client_acceptance_descriptor_is_required_and_bound(
    tmp_path: Path,
) -> None:
    config_path, _source_archive = write_private_runner_config(
        tmp_path, include_client_identity=True
    )

    loaded = lane.load_config(config_path, config_path.parent / CLIENT_ACCEPTANCE_NAME)

    assert loaded["clientAcceptance"]["format"] == lane.CLIENT_ACCEPTANCE_FORMAT
    assert loaded["clientAcceptance"]["ripdpiSourceSha"] == "d" * 40
    assert loaded["clientAcceptance"]["apkSha256"] == "e" * 64


def test_client_acceptance_descriptor_missing_or_symlink_fails_closed(
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
    assert manifest["clientAcceptance"]["pass"] is False
    assert manifest["clientAcceptance"]["ripdpiSourceSha"] == "0" * 40

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    config_path, _source_archive = write_private_runner_config(symlink_root)
    descriptor = config_path.parent / CLIENT_ACCEPTANCE_NAME
    replacement = config_path.parent / "replacement.json"
    replacement.write_text(descriptor.read_text())
    replacement.chmod(0o600)
    descriptor.unlink()
    descriptor.symlink_to(replacement)
    with pytest.raises(ValueError, match="absolute regular file"):
        lane.load_config(config_path, descriptor)


def test_client_acceptance_requires_manifest_v4() -> None:
    assert lane.MANIFEST_VERSION == "real_vps_awg_nat_evidence_v4"
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    lane.validate_manifest(manifest, expected_source_sha="1" * 40, now=2_000_000_000)
    manifest["version"] = "real_vps_awg_nat_evidence_v2"
    with pytest.raises(ValueError, match="unsupported manifest version"):
        lane.validate_manifest(
            manifest, expected_source_sha="1" * 40, now=2_000_000_000
        )


def test_loaded_client_acceptance_is_retained_in_preflight_failure(
    tmp_path: Path,
) -> None:
    config_path, source_archive = write_private_runner_config(tmp_path)
    manifest = run_with_private_config(
        config_path, source_archive, tmp_path / "out.json"
    )

    assert manifest["classification"] == "INFRA_UNAVAILABLE"
    assert manifest["reasonCode"] == "PREREQUISITE_MISSING"
    assert manifest["clientAcceptance"]["ripdpiSourceSha"] == "d" * 40
    assert manifest["clientAcceptance"]["apkSha256"] == "e" * 64


def test_loaded_client_acceptance_is_retained_when_executor_start_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path, source_archive = write_private_runner_config(tmp_path)
    loaded = lane.load_config(config_path, config_path.parent / CLIENT_ACCEPTANCE_NAME)
    monkeypatch.setattr(lane, "load_config", lambda _path, _descriptor=None: loaded)
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
    assert manifest["clientAcceptance"]["ripdpiSourceSha"] == "d" * 40
    assert manifest["clientAcceptance"]["apkSha256"] == "e" * 64


def test_client_acceptance_descriptor_rejects_placeholder_digests(
    tmp_path: Path,
) -> None:
    config_path, _source_archive = write_private_runner_config(tmp_path)
    descriptor = config_path.parent / CLIENT_ACCEPTANCE_NAME
    descriptor.write_bytes(
        lane.canonical_json_bytes(live_client_acceptance(ripdpiSourceSha="0" * 40))
    )
    descriptor.chmod(0o600)

    with pytest.raises(ValueError, match="real source, APK, and report"):
        lane.load_config(config_path, descriptor)


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
                "--client-acceptance-descriptor",
                str(config_path.parent / CLIENT_ACCEPTANCE_NAME),
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


def test_manifest_client_acceptance_is_bound_to_expected_artifacts() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    lane.validate_manifest(
        manifest,
        expected_source_sha="1" * 40,
        expected_engine_commit="a" * 40,
        expected_engine_binary_sha256="b" * 64,
        expected_client_source_sha="d" * 40,
        expected_client_apk_sha256="e" * 64,
        expected_client_report_sha256="f" * 64,
        expected_client_correlation_sha256=manifest["clientAcceptance"][
            "correlationSha256"
        ],
        now=2_000_000_000,
    )
    manifest["clientAcceptance"]["apkSha256"] = "a" * 64
    manifest["clientAcceptance"]["correlationSha256"] = (
        lane.client_acceptance_correlation(manifest["clientAcceptance"])
    )
    with pytest.raises(ValueError, match="client APK SHA mismatch"):
        lane.validate_manifest(
            manifest,
            expected_source_sha="1" * 40,
            expected_client_source_sha="d" * 40,
            expected_client_apk_sha256="e" * 64,
            now=2_000_000_000,
        )


def test_manifest_rejects_missing_short_or_mismatched_engine_digests() -> None:
    baseline = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    for mutate, error in (
        (
            lambda value: value["engineIdentity"].pop("amneziawgGoCommit"),
            "fields differ",
        ),
        (
            lambda value: value["engineIdentity"].update(
                amneziawgGoBinarySha256="b" * 63
            ),
            "engine binary SHA",
        ),
        (
            lambda value: None,
            "engine commit mismatch",
        ),
    ):
        manifest = copy.deepcopy(baseline)
        mutate(manifest)
        with pytest.raises(ValueError, match=error):
            lane.validate_manifest(
                manifest,
                expected_source_sha="1" * 40,
                expected_engine_commit="c" * 40,
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
    assert "create-client-acceptance-request" in workflow
    assert "consume-client-acceptance" in workflow
    assert "--request" in workflow
    assert workflow.count('--invocation-attempt "$invocation_attempt"') >= 3
    assert "grep -Fx 'ED25519 Public-Key:'" in workflow
    assert '"$inbox_dir/${nonce}.json"' in workflow
    assert "umask 077" in workflow
    assert "--client-acceptance-descriptor" in workflow
    assert "real-vps-awg-client-acceptance.pub" in workflow
    assert "--executor github_actions" in workflow
    assert "--expected-executor github_actions" in workflow
    assert "trap cleanup EXIT" in workflow
    assert "record-recurring" in workflow
    assert "run_status=$?" in workflow
    assert "validate_status=$?" in workflow
    assert "--allow-non-pass" in workflow
    assert "if (( run_status == 0 && validate_status == 0 )); then" in workflow
    assert "if (( structural_status == 0 )); then" in workflow
    assert (
        "evidence_dir=/var/lib/ripdpi-real-vps-awg-nat/evidence/github-actions"
        in workflow
    )
    assert 'LOCK_DIR="/run/lock/ripdpi-real-vps-awg-nat"' in workflow
    assert "flock -n 9" in workflow
    assert 'install -o root -g root -m 0600 "$current"' not in workflow
    assert 'mv -f -- "$temporary" "$latest"' not in workflow


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


def test_public_schema_rejects_executor_entrypoint_substitution() -> None:
    schema = json.loads(
        (REPO_ROOT / "contract/real-vps-awg-nat-evidence.schema.json").read_text()
    )
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    manifest["provenance"]["entrypointPath"] = lane.LOCAL_ENTRYPOINT_PATH
    assert list(Draft202012Validator(schema).iter_errors(manifest))

    manifest["provenance"]["executor"] = "local_systemd"
    manifest["provenance"]["entrypointPath"] = lane.WORKFLOW_PATH
    assert list(Draft202012Validator(schema).iter_errors(manifest))


def test_manifest_rejects_reversed_client_and_run_windows() -> None:
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    manifest["clientAcceptance"]["startedAtEpoch"] = manifest["finishedAtEpoch"] + 61
    manifest["clientAcceptance"]["finishedAtEpoch"] = manifest["finishedAtEpoch"] + 62
    manifest["clientAcceptance"]["correlationSha256"] = (
        lane.client_acceptance_correlation(manifest["clientAcceptance"])
    )

    with pytest.raises(ValueError, match="outside the run window"):
        lane.validate_manifest(
            manifest, expected_source_sha="1" * 40, now=2_000_000_120
        )


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
            "--client-acceptance-descriptor",
            str(tmp_path / "missing-client-acceptance.json"),
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
    assert '--invocation-attempt "$invocation_attempt"' in launcher
    assert "${safe_invocation}.json" in launcher
    assert "grep -Fx 'ED25519 Public-Key:'" in launcher
    assert 'CONFIG="/etc/ripdpi/real-vps-awg-nat-local.json"' in launcher
    assert "accepts no arguments" in launcher
    assert 'cmp -s "$RUNNER"' in launcher
    for installed_path in (
        "/etc/systemd/system/ripdpi-real-vps-awg-nat.service",
        "/etc/systemd/system/ripdpi-real-vps-awg-nat.timer",
        "/usr/lib/tmpfiles.d/ripdpi-real-vps-awg-nat.conf",
    ):
        assert f"cmp -s {installed_path}" in launcher
    assert 'rm -f -- "$evidence_dir/latest.json"' not in launcher
    assert "record-recurring" in launcher
    assert "--lock-fd 9" in launcher
    assert 'mv -f -- "$evidence_dir/.latest.json.tmp"' not in launcher
    assert "--allow-non-pass" in launcher
    assert 'quarantine="$quarantine_dir/invalid-' in launcher
    assert "run_status == 0 && validate_status == 0" in launcher
    assert "validate-client-runtime" in launcher
    assert "validate-client-acceptance" in launcher
    assert "create-client-acceptance-request" in launcher
    assert "consume-client-acceptance" in launcher
    assert '--client-acceptance-descriptor "$consumed_acceptance"' in launcher
    assert launcher.index("create-client-acceptance-request") < launcher.index(
        "consume-client-acceptance"
    )
    assert 'PATH="$(dirname "$client_binary"):$PATH"' in launcher
    assert launcher.count("--expected-client-source-sha") == 3
    assert launcher.count("--expected-client-apk-sha256") == 3
    assert launcher.count("--expected-client-report-sha256") == 3
    assert launcher.count("--expected-client-correlation-sha256") == 3
    assert "GITHUB_" not in launcher


def test_runtime_engine_identity_binds_actual_toolchain_binary(tmp_path: Path) -> None:
    toolchain = tmp_path / "toolchains" / ("a" * 64)
    binary_dir = toolchain / "bin"
    binary_dir.mkdir(parents=True, mode=0o700)
    binary = binary_dir / "amneziawg-go"
    binary.write_bytes(b"exact-awg-runtime")
    binary.chmod(0o700)
    artifact_sha = lane.sha256_bytes(binary.read_bytes())
    source_sha = "b" * 40
    manifest = {
        "schemaVersion": 1,
        "inputs": {
            "goBundleSha256": "c" * 64,
            "goCommit": source_sha,
            "toolsBundleSha256": "d" * 64,
            "toolsCommit": "e" * 40,
            "vendorSha256": "f" * 64,
        },
        "binaries": {
            "amneziawg-go": artifact_sha,
            "awg": "1" * 64,
            "awg-quick": "2" * 64,
        },
        "treeSha256": "3" * 64,
    }
    manifest_path = toolchain / "manifest.json"
    manifest_path.write_bytes(lane.canonical_json_bytes(manifest))
    manifest_path.chmod(0o600)
    assert lane.validate_runtime_engine_identity(binary) == {
        "amneziawgGoBinarySha256": artifact_sha,
        "amneziawgGoCommit": source_sha,
    }
    binary.write_bytes(b"replaced-runtime")
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        lane.validate_runtime_engine_identity(binary)


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
    assert 'rm -f -- "$evidence_dir/latest.json"' not in launcher
    assert 'rm -f -- "$evidence_dir/.latest.json.tmp"' not in launcher
    assert "record-recurring" in launcher
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
        "openssl",
        "python3",
        "rm",
        "sha256sum",
        "sleep",
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
        "openssl",
        "python3",
        "rm",
        "sha256sum",
        "sleep",
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
    assert manifest["clientAcceptance"]["ripdpiSourceSha"] == "0" * 40
    assert manifest["clientAcceptance"]["apkSha256"] == "0" * 64
    assert manifest["clientAcceptance"]["pass"] is False
    assert manifest["engineIdentity"]["amneziawgGoCommit"] == "0" * 40


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
    assert 'latest="$evidence_dir/latest.json"' in installer
    assert "archive_legacy_latest()" in installer
    assert "prepare-retained-state" in installer
    assert '--expected-source-sha "$source_sha"' in installer
    assert (
        'CLIENT_ACCEPTANCE_PUBLIC_KEY="/etc/ripdpi/real-vps-awg-client-acceptance.pub"'
        in installer
    )
    assert (
        'openssl pkey -pubin -in "$CLIENT_ACCEPTANCE_PUBLIC_KEY" -text -noout'
        in installer
    )
    assert "grep -Fx 'ED25519 Public-Key:'" in installer
    install_success = installer.index(
        "systemctl enable --now ripdpi-real-vps-awg-nat.timer"
    )
    archive_call = installer.rindex(
        '\nif ! archive_legacy_latest || ! "$RUNNER" prepare-retained-state \\\n'
    )
    assert archive_call < install_success
    assert installer.count('latest="$evidence_dir/latest.json"') == 1
    assert "archive_legacy_latest;" not in installer[:archive_call]
    assert (
        "rm -f -- \\\n  /var/lib/ripdpi-real-vps-awg-nat/evidence/latest.json"
        not in installer
    )
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


def test_manifest_v4_separates_engine_from_real_ripdpi_client_acceptance() -> None:
    acceptance = live_client_acceptance()
    engine = {
        "amneziawgGoCommit": "a" * 40,
        "amneziawgGoBinarySha256": "b" * 64,
    }
    cfg = config()
    cfg.update({"engineIdentity": engine, "clientAcceptance": acceptance})

    manifest = lane.run_lane(cfg, FakeExecutor(), metadata(), now=lambda: 2_000_000_000)

    assert manifest["version"] == "real_vps_awg_nat_evidence_v4"
    assert manifest["engineIdentity"] == engine
    assert manifest["clientAcceptance"] == acceptance
    assert "clientIdentity" not in manifest
    lane.validate_manifest(manifest, expected_source_sha="1" * 40, now=2_000_000_000)


def test_public_manifest_schema_accepts_v4_and_rejects_engine_as_client() -> None:
    schema = json.loads(
        (REPO_ROOT / "contract/real-vps-awg-nat-evidence.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    manifest = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    Draft202012Validator(schema).validate(manifest)

    manifest["clientAcceptance"] = manifest["engineIdentity"]
    errors = list(Draft202012Validator(schema).iter_errors(manifest))
    assert errors


def test_schema_and_python_share_strict_pass_semantics() -> None:
    schema = json.loads(
        (REPO_ROOT / "contract/real-vps-awg-nat-evidence.schema.json").read_text()
    )
    validator = Draft202012Validator(schema)
    baseline = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    for mutate in (
        lambda value: value["clientAcceptance"].update({"pass": False}),
        lambda value: value["clientAcceptance"]["outcomes"].update(routedTcp=False),
        lambda value: value["clientAcceptance"].update(ripdpiSourceSha="0" * 40),
        lambda value: value["clientAcceptance"].update(apkSha256="0" * 64),
        lambda value: value["clientAcceptance"].update(reportSha256="0" * 64),
        lambda value: value.update(runnerIdSha256="0" * 64),
        lambda value: value["provenance"].update(sourceArchiveSha256="0" * 64),
        lambda value: value["producerDigests"].update(runnerSha256="0" * 64),
        lambda value: value.update(privateLogSha256="0" * 64),
        lambda value: value["serverDeployment"].update(receiptSha256="0" * 64),
        lambda value: value["captureDigests"].__setitem__(0, "0" * 64),
        lambda value: value["phases"][1]["tcp"].update(ok=False, durationMs=None),
        lambda value: value["phases"][3]["server"].update(handshakeFresh=True),
        lambda value: value["phases"][3]["server"].update(peerRxDelta=1),
        lambda value: value["phases"][2]["server"].update(
            serviceGenerationChanged=False
        ),
        lambda value: value["phases"][3]["server"].update(
            configGenerationChanged=False
        ),
    ):
        manifest = copy.deepcopy(baseline)
        mutate(manifest)
        manifest["clientAcceptance"]["correlationSha256"] = (
            lane.client_acceptance_correlation(manifest["clientAcceptance"])
        )
        assert list(validator.iter_errors(manifest))
        with pytest.raises(ValueError):
            lane.validate_manifest(
                manifest, expected_source_sha="1" * 40, now=2_000_000_000
            )


def test_schema_is_structural_and_executable_validator_owns_cross_field_rules() -> None:
    schema = json.loads(
        (REPO_ROOT / "contract/real-vps-awg-nat-evidence.schema.json").read_text()
    )
    validator = Draft202012Validator(schema)
    assert "Structural validation only" in schema["$comment"]
    assert "canonical executable validator" in schema["$comment"]
    baseline = lane.run_lane(
        config(), FakeExecutor(), metadata(), now=lambda: 2_000_000_000
    )
    for mutate, error in (
        (
            lambda value: value["clientAcceptance"].update(correlationSha256="a" * 64),
            "correlation",
        ),
        (
            lambda value: value.update(
                startedAtEpoch=2_000_000_001,
                finishedAtEpoch=2_000_000_000,
                generatedAtEpoch=2_000_000_000,
            ),
            "timestamps",
        ),
        (
            lambda value: value["clientAcceptance"].update(
                startedAtEpoch=2_000_000_001,
                finishedAtEpoch=2_000_000_000,
            ),
            "timestamps",
        ),
    ):
        manifest = copy.deepcopy(baseline)
        mutate(manifest)
        assert list(validator.iter_errors(manifest)) == []
        with pytest.raises(ValueError, match=error):
            lane.validate_manifest(
                manifest, expected_source_sha="1" * 40, now=2_000_000_100
            )


def test_signed_nonce_handoff_supports_initial_then_recurring_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "runner").mkdir(mode=0o700)
    config_path, source_archive = write_private_runner_config(
        tmp_path / "runner", include_client_identity=False
    )
    real_euid = os.geteuid()
    real_load_config = lane.load_config

    def load_user_owned_config(*args):
        root_geteuid = lane.os.geteuid
        lane.os.geteuid = lambda: real_euid
        try:
            return real_load_config(*args)
        finally:
            lane.os.geteuid = root_geteuid

    manifests = []
    current = int(time.time())
    for index, (started, finished) in enumerate(
        ((current - 100, current - 80), (current - 40, current - 20)),
        start=1,
    ):
        invocation_id = f"local-{index}"
        request = tmp_path / str(index) / "request.json"
        request.parent.mkdir(parents=True, exist_ok=True)
        request.parent.chmod(0o700)
        nonce = lane.create_client_acceptance_request(
            request, invocation_id, now=started - 10, valid_seconds=300
        )
        acceptance = live_client_acceptance(
            reportSha256=str(index) * 64,
            startedAtEpoch=started,
            finishedAtEpoch=finished,
        )
        descriptor, public_key = signed_client_handoff(
            tmp_path / str(index),
            acceptance,
            nonce=nonce,
            invocation_id=invocation_id,
        )
        output = descriptor.parent / "consumed.json"
        assert (
            lane.main(
                [
                    "consume-client-acceptance",
                    "--descriptor",
                    str(descriptor),
                    "--public-key",
                    str(public_key),
                    "--request",
                    str(request),
                    "--invocation-id",
                    invocation_id,
                    "--invocation-attempt",
                    "1",
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
        assert not descriptor.exists()
        assert not request.exists()
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        manifest_path = descriptor.parent / "manifest.json"
        with monkeypatch.context() as root_context:
            root_context.setattr(lane.os, "geteuid", lambda: 0)
            root_context.setattr(lane.time, "time", lambda value=finished + 10: value)
            root_context.setattr(lane, "load_config", load_user_owned_config)
            root_context.setattr(lane.shutil, "which", lambda _command: "/usr/bin/tool")
            root_context.setattr(
                lane,
                "validate_runtime_engine_identity",
                lambda _path: {
                    "amneziawgGoCommit": "c" * 40,
                    "amneziawgGoBinarySha256": "d" * 64,
                },
            )
            root_context.setattr(lane, "SystemExecutor", lambda _config: FakeExecutor())
            assert (
                lane.main(
                    [
                        "run",
                        "--config",
                        str(config_path),
                        "--output",
                        str(manifest_path),
                        "--source-sha",
                        "1" * 40,
                        "--source-archive",
                        str(source_archive),
                        "--executor",
                        "local_systemd",
                        "--entrypoint-path",
                        lane.LOCAL_ENTRYPOINT_PATH,
                        "--invocation-id",
                        invocation_id,
                        "--invocation-attempt",
                        "1",
                        "--client-acceptance-descriptor",
                        str(output),
                    ]
                )
                == 0
            )
        manifests.append(json.loads(manifest_path.read_text()))

    lane.validate_recurring_pair(manifests[0], manifests[1], now=current)


def test_client_acceptance_requests_are_unique_private_and_bounded(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = lane.create_client_acceptance_request(
        first_path, "local-first", now=2_000_000_000, valid_seconds=300
    )
    second = lane.create_client_acceptance_request(
        second_path, "local-second", now=2_000_000_001, valid_seconds=1
    )

    assert first != second
    assert first != "0" * 64 and second != "0" * 64
    assert stat.S_IMODE(first_path.stat().st_mode) == 0o600
    assert json.loads(first_path.read_text()) == {
        "format": "ripdpi_awg_live_acceptance_request_v1",
        "invocationId": "local-first",
        "invocationAttempt": 1,
        "nonce": first,
        "generatedAtEpoch": 2_000_000_000,
        "expiresAtEpoch": 2_000_000_300,
    }
    with pytest.raises(ValueError, match="lifetime"):
        lane.create_client_acceptance_request(
            tmp_path / "invalid.json", "local-invalid", valid_seconds=301
        )
    unsafe_parent = tmp_path / "unsafe"
    unsafe_parent.mkdir(mode=0o755)
    unsafe_parent.chmod(0o755)
    with pytest.raises(ValueError, match="output directory is unsafe"):
        lane.create_client_acceptance_request(
            unsafe_parent / "request.json", "local-unsafe"
        )


def test_signed_handoff_rejects_replay_mutation_and_wrong_nonce(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    nonce = lane.create_client_acceptance_request(
        request, "local-a", now=1_999_999_900, valid_seconds=300
    )
    descriptor, public_key = signed_client_handoff(
        tmp_path,
        live_client_acceptance(),
        nonce=nonce,
        invocation_id="local-a",
        invocation_attempt=2,
    )
    envelope = json.loads(descriptor.read_text())
    for mutate in (
        lambda value: value.update(nonce="b" * 64),
        lambda value: value.update(invocationId="local-b"),
        lambda value: value.update(invocationAttempt=1),
        lambda value: value["acceptance"].update(reportSha256="1" * 64),
    ):
        candidate = copy.deepcopy(envelope)
        mutate(candidate)
        descriptor.write_bytes(lane.canonical_json_bytes(candidate))
        with pytest.raises(ValueError):
            lane.consume_client_acceptance_handoff(
                descriptor,
                public_key,
                request=request,
                expected_invocation_id="local-a",
                expected_invocation_attempt=2,
                output=tmp_path / "consumed.json",
                now=2_000_000_000,
            )
        assert descriptor.exists()
        assert request.exists()
        assert not (tmp_path / "consumed.json").exists()


def test_signed_handoff_rejects_non_ed25519_public_key(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    nonce = lane.create_client_acceptance_request(
        request, "local-a", invocation_attempt=1, now=1_999_999_900
    )
    descriptor, _ed25519_key = signed_client_handoff(
        tmp_path / "handoff",
        live_client_acceptance(),
        nonce=nonce,
        invocation_id="local-a",
    )
    rsa_private = tmp_path / "rsa-private.pem"
    rsa_public = tmp_path / "rsa-public.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-out", rsa_private],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", rsa_private, "-pubout", "-out", rsa_public],
        check=True,
        capture_output=True,
    )
    rsa_public.chmod(0o600)

    with pytest.raises(ValueError, match="Ed25519"):
        lane.consume_client_acceptance_handoff(
            descriptor,
            rsa_public,
            request=request,
            expected_invocation_id="local-a",
            expected_invocation_attempt=1,
            output=tmp_path / "consumed.json",
            now=2_000_000_000,
        )


def test_github_rerun_uses_distinct_signed_invocation_attempts(tmp_path: Path) -> None:
    current = 2_000_000_000
    manifests = []
    for attempt in (1, 2):
        root = tmp_path / str(attempt)
        root.mkdir(mode=0o700)
        request = root / "request.json"
        nonce = lane.create_client_acceptance_request(
            request, "github-42", invocation_attempt=attempt, now=current - 20
        )
        descriptor, public_key = signed_client_handoff(
            root,
            live_client_acceptance(
                reportSha256=str(attempt) * 64,
                startedAtEpoch=current - 30 + attempt * 15,
                finishedAtEpoch=current - 25 + attempt * 15,
            ),
            nonce=nonce,
            invocation_id="github-42",
            invocation_attempt=attempt,
        )
        output = root / "consumed.json"
        lane.consume_client_acceptance_handoff(
            descriptor,
            public_key,
            request=request,
            expected_invocation_id="github-42",
            expected_invocation_attempt=attempt,
            output=output,
            now=current,
        )
        manifest = lane.run_lane(
            config(),
            FakeExecutor(),
            {**metadata(), "invocationId": "github-42", "invocationAttempt": attempt},
            now=lambda value=current + attempt: value,
        )
        manifest["clientAcceptance"] = json.loads(output.read_text())
        manifests.append(manifest)
    lane.validate_recurring_pair(manifests[0], manifests[1], now=current + 10)


def recurring_manifest(index: int, *, source: str = "1" * 40) -> dict:
    started = 2_000_000_000 + index * 100
    manifest = lane.run_lane(
        config(),
        FakeExecutor(),
        {
            **metadata(),
            "sourceSha": source,
            "invocationId": f"recurring-{index}",
            "invocationAttempt": index,
        },
        now=lambda: started,
    )
    acceptance = live_client_acceptance(
        reportSha256=f"{index % 10}" * 64,
        startedAtEpoch=started - 20,
        finishedAtEpoch=started - 10,
    )
    manifest["clientAcceptance"] = acceptance
    return manifest


def test_recurring_state_requires_valid_initial_then_valid_pair(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    lock = tmp_path / "lane.lock"
    first = recurring_manifest(1)
    second = recurring_manifest(2)

    assert (
        lane.record_recurring_state(first, state, lock_path=lock, now=2_000_000_300)
        == "pending"
    )
    assert json.loads((state / "pending-initial.json").read_text()) == first
    assert not (state / "latest.json").exists()
    assert (
        lane.record_recurring_state(second, state, lock_path=lock, now=2_000_000_300)
        == "published"
    )
    assert json.loads((state / "latest.json").read_text()) == second
    assert not (state / "pending-initial.json").exists()
    assert stat.S_IMODE((state / "latest.json").stat().st_mode) == 0o600


def test_recurring_state_accepts_weekly_timer_jitter(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    lock = tmp_path / "lane.lock"
    first = recurring_manifest(1)
    later = recurring_manifest(2)
    later_epoch = first["generatedAtEpoch"] + 7 * 24 * 60 * 60 + 30 * 60
    later.update(
        startedAtEpoch=later_epoch,
        finishedAtEpoch=later_epoch,
        generatedAtEpoch=later_epoch,
    )
    later["clientAcceptance"].update(
        startedAtEpoch=later_epoch - 20,
        finishedAtEpoch=later_epoch - 10,
    )
    later["clientAcceptance"]["correlationSha256"] = lane.client_acceptance_correlation(
        later["clientAcceptance"]
    )

    assert (
        lane.record_recurring_state(
            first, state, lock_path=lock, now=first["generatedAtEpoch"]
        )
        == "pending"
    )
    assert (
        lane.record_recurring_state(later, state, lock_path=lock, now=later_epoch)
        == "published"
    )


@pytest.mark.parametrize("retained_name", ["pending-initial.json", "latest.json"])
@pytest.mark.parametrize("prior_age", [300, 16 * 24 * 60 * 60])
def test_recurring_state_archives_prior_source_generation(
    tmp_path: Path, retained_name: str, prior_age: int
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    prior = recurring_manifest(1, source="1" * 40)
    prior_epoch = 2_000_000_300 - prior_age
    prior.update(
        startedAtEpoch=prior_epoch - 100,
        finishedAtEpoch=prior_epoch,
        generatedAtEpoch=prior_epoch,
    )
    prior["clientAcceptance"].update(
        startedAtEpoch=prior_epoch - 120,
        finishedAtEpoch=prior_epoch - 110,
    )
    prior["clientAcceptance"]["correlationSha256"] = lane.client_acceptance_correlation(
        prior["clientAcceptance"]
    )
    retained = state / retained_name
    retained.write_bytes(lane.canonical_json_bytes(prior))
    retained.chmod(0o600)
    current = recurring_manifest(2, source="2" * 40)

    assert (
        lane.record_recurring_state(
            current,
            state,
            lock_path=tmp_path / "lane.lock",
            now=2_000_000_300,
        )
        == "pending"
    )

    assert json.loads((state / "pending-initial.json").read_text()) == current
    assert not (state / "latest.json").exists()
    archived = list((state / "history").glob(f"{retained.stem}-*.json"))
    assert len(archived) == 1
    assert archived[0].read_bytes() == lane.canonical_json_bytes(prior)
    assert stat.S_IMODE(archived[0].stat().st_mode) == 0o600


def test_invalid_initial_cannot_poison_pending_or_latest(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    manifest = recurring_manifest(1)
    manifest["clientAcceptance"]["correlationSha256"] = "a" * 64

    with pytest.raises(ValueError, match="correlation"):
        lane.record_recurring_state(
            manifest, state, lock_path=tmp_path / "lane.lock", now=2_000_000_300
        )

    assert list(state.iterdir()) == []


def test_invalid_recurring_attempt_preserves_exact_pending_bytes(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    lock = tmp_path / "lane.lock"
    first = recurring_manifest(1)
    lane.record_recurring_state(first, state, lock_path=lock, now=2_000_000_300)
    before = (state / "pending-initial.json").read_bytes()
    invalid = recurring_manifest(2)
    invalid["clientAcceptance"]["correlationSha256"] = "a" * 64

    with pytest.raises(ValueError, match="correlation"):
        lane.record_recurring_state(invalid, state, lock_path=lock, now=2_000_000_300)

    assert (state / "pending-initial.json").read_bytes() == before
    assert not (state / "latest.json").exists()


def test_recurring_state_replays_durable_latest_before_pending_cleanup(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    first = recurring_manifest(1)
    second = recurring_manifest(2)
    lane.record_recurring_state(
        first, state, lock_path=tmp_path / "lane.lock", now=2_000_000_300
    )

    with pytest.raises(lane.RecurringStateInterrupted):
        lane.record_recurring_state(
            second,
            state,
            lock_path=tmp_path / "lane.lock",
            now=2_000_000_300,
            failpoint="after-latest-replace",
        )

    assert (state / "pending-initial.json").exists()
    assert json.loads((state / "latest.json").read_text()) == second
    assert (
        lane.record_recurring_state(
            second, state, lock_path=tmp_path / "lane.lock", now=2_000_000_300
        )
        == "published"
    )
    assert not (state / "pending-initial.json").exists()


def test_recurring_state_recovers_fsynced_initial_and_truncated_temporary(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    first = recurring_manifest(1)
    lock = tmp_path / "lane.lock"
    with pytest.raises(lane.RecurringStateInterrupted):
        lane.record_recurring_state(
            first,
            state,
            lock_path=lock,
            now=2_000_000_300,
            failpoint="after-pending-initial-temp-fsync",
        )
    assert not (state / "pending-initial.json").exists()
    assert (state / ".pending-initial.json.tmp").exists()
    assert (
        lane.record_recurring_state(first, state, lock_path=lock, now=2_000_000_300)
        == "pending"
    )

    (state / ".latest.json.tmp").write_text("{")
    (state / ".latest.json.tmp").chmod(0o600)
    second = recurring_manifest(2)
    assert (
        lane.record_recurring_state(second, state, lock_path=lock, now=2_000_000_300)
        == "published"
    )
    assert not (state / ".latest.json.tmp").exists()


def test_recurring_state_replays_pending_replace_idempotently(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    first = recurring_manifest(1)
    lock = tmp_path / "lane.lock"
    with pytest.raises(lane.RecurringStateInterrupted):
        lane.record_recurring_state(
            first,
            state,
            lock_path=lock,
            now=2_000_000_300,
            failpoint="after-pending-initial-replace",
        )
    before = (state / "pending-initial.json").read_bytes()
    assert (
        lane.record_recurring_state(first, state, lock_path=lock, now=2_000_000_300)
        == "pending"
    )
    assert (state / "pending-initial.json").read_bytes() == before


def test_recurring_state_refuses_foreign_recovery_and_invalid_latest(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    first = recurring_manifest(1)
    lock = tmp_path / "lane.lock"
    lane.record_recurring_state(first, state, lock_path=lock, now=2_000_000_300)
    bad = state / ".latest.json.tmp"
    bad.write_text("{}\n")
    bad.chmod(0o644)
    before = (state / "pending-initial.json").read_bytes()
    with pytest.raises(ValueError, match="unsafe metadata"):
        lane.record_recurring_state(
            recurring_manifest(2), state, lock_path=lock, now=2_000_000_300
        )
    assert (state / "pending-initial.json").read_bytes() == before
    assert bad.exists()

    bad.unlink()
    invalid = json.loads(before)
    invalid["clientAcceptance"]["correlationSha256"] = "a" * 64
    (state / "pending-initial.json").write_bytes(lane.canonical_json_bytes(invalid))
    with pytest.raises(ValueError, match="correlation"):
        lane.record_recurring_state(
            recurring_manifest(2), state, lock_path=lock, now=2_000_000_300
        )


def test_recurring_state_lock_blocks_parallel_controller(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    lock = tmp_path / "lane.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    os.fchmod(descriptor, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(lane.RecurringStateBusy):
            lane.record_recurring_state(
                recurring_manifest(1), state, lock_path=lock, now=2_000_000_300
            )
    finally:
        os.close(descriptor)
    assert list(state.iterdir()) == []


def test_retained_v4_manifest_uses_executable_semantic_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lane.time, "time", lambda: 2_000_000_300)
    manifest = recurring_manifest(1)
    path = tmp_path / "latest.json"
    path.write_bytes(lane.canonical_json_bytes(manifest))
    path.chmod(0o600)
    assert lane.main(["validate-retained-pass", "--manifest", str(path)]) == 0

    manifest["clientAcceptance"]["correlationSha256"] = "a" * 64
    path.write_bytes(lane.canonical_json_bytes(manifest))
    assert lane.main(["validate-retained-pass", "--manifest", str(path)]) == 1


def test_installer_prepares_both_retained_generation_slots(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    lock = tmp_path / "lane.lock"
    for index, name in enumerate(("pending-initial.json", "latest.json"), start=1):
        retained = recurring_manifest(index, source="1" * 40)
        path = state / name
        path.write_bytes(lane.canonical_json_bytes(retained))
        path.chmod(0o600)

    lane.prepare_retained_state(
        state,
        current_source_sha="2" * 40,
        lock_path=lock,
        now=2_000_000_300,
    )

    assert not (state / "pending-initial.json").exists()
    assert not (state / "latest.json").exists()
    assert len(list((state / "history").glob("*.json"))) == 2


def test_installer_refuses_stale_current_generation_state(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    retained = recurring_manifest(1)
    path = state / "latest.json"
    path.write_bytes(lane.canonical_json_bytes(retained))
    path.chmod(0o600)

    with pytest.raises(ValueError, match="stale"):
        lane.prepare_retained_state(
            state,
            current_source_sha="1" * 40,
            lock_path=tmp_path / "lane.lock",
            now=retained["generatedAtEpoch"] + lane.RECURRING_PAIR_MAX_AGE_SECONDS + 1,
        )

    assert path.read_bytes() == lane.canonical_json_bytes(retained)


def test_signed_handoff_rejects_expired_request(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    nonce = lane.create_client_acceptance_request(
        request, "local-expired", now=1_999_999_000, valid_seconds=300
    )
    descriptor, public_key = signed_client_handoff(
        tmp_path,
        live_client_acceptance(),
        nonce=nonce,
        invocation_id="local-expired",
    )

    with pytest.raises(ValueError, match="request expired"):
        lane.consume_client_acceptance_handoff(
            descriptor,
            public_key,
            request=request,
            expected_invocation_id="local-expired",
            output=tmp_path / "consumed.json",
            now=2_000_000_000,
        )


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update(format="ripdpi_awg_client_identity_v1"), "format"),
        (lambda value: value.update(ripdpiSourceSha="a" * 39), "source"),
        (lambda value: value.update(apkSha256="a" * 63), "APK"),
        (lambda value: value.update(reportSha256="a" * 63), "report"),
        (lambda value: value.update(correlationSha256="a" * 64), "correlation"),
        (lambda value: value.update(startedAtEpoch=2_000_000_001), "timestamps"),
        (lambda value: value.update(finishedAtEpoch=2_000_000_061), "future"),
        (
            lambda value: value.update(
                startedAtEpoch=1_999_989_900, finishedAtEpoch=1_999_990_000
            ),
            "stale",
        ),
        (lambda value: value.update(transport="wireguard"), "transport"),
        (lambda value: value.update({"pass": False}), "PASS"),
        (
            lambda value: value["outcomes"].update(routedTcp=False),
            "outcomes",
        ),
        (
            lambda value: value["outcomes"].update(routedUdp=False),
            "outcomes",
        ),
        (
            lambda value: value["outcomes"].update(recovery=False),
            "outcomes",
        ),
        (
            lambda value: value["outcomes"].update(staleKeyRejected=False),
            "outcomes",
        ),
        (
            lambda value: value["outcomes"].update(cleanup=False),
            "outcomes",
        ),
    ],
)
def test_client_acceptance_negative_matrix(mutation, error: str) -> None:
    value = live_client_acceptance()
    mutation(value)
    with pytest.raises(ValueError, match=error):
        lane.validate_client_acceptance(value, now=2_000_000_000, max_age_seconds=300)


def test_client_acceptance_rejects_zero_report_with_recomputed_correlation() -> None:
    value = live_client_acceptance(reportSha256="0" * 64)
    with pytest.raises(ValueError, match="real source, APK, and report"):
        lane.validate_client_acceptance(value, now=2_000_000_000)


@pytest.mark.parametrize(
    "field",
    [
        "ripdpiSourceSha",
        "apkSha256",
        "reportSha256",
        "correlationSha256",
    ],
)
def test_client_acceptance_rejects_missing_digest(field: str) -> None:
    value = live_client_acceptance()
    del value[field]

    with pytest.raises(ValueError, match="fields differ"):
        lane.validate_client_acceptance(value, now=2_000_000_000)


def test_client_acceptance_descriptor_is_canonical_private_and_inode_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = tmp_path / "real-vps-awg-client-acceptance.json"
    value = live_client_acceptance()
    descriptor.write_bytes(lane.canonical_json_bytes(value))
    descriptor.chmod(0o600)
    assert lane.client_acceptance_descriptor(descriptor, now=2_000_000_000) == value

    descriptor.chmod(0o644)
    with pytest.raises(ValueError, match="unsafe|unavailable"):
        lane.client_acceptance_descriptor(descriptor, now=2_000_000_000)
    descriptor.chmod(0o600)
    descriptor.write_bytes(b"{" + b"x" * 4096 + b"}")
    with pytest.raises(ValueError, match="unavailable"):
        lane.client_acceptance_descriptor(descriptor, now=2_000_000_000)

    descriptor.write_bytes(lane.canonical_json_bytes(value))
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(lane.canonical_json_bytes(value))
    replacement.chmod(0o600)
    real_open = os.open

    def replacing_open(path, flags, mode=0o600):
        if Path(path) == descriptor:
            os.replace(replacement, descriptor)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", replacing_open)
    with pytest.raises(ValueError, match="unavailable"):
        lane.client_acceptance_descriptor(descriptor, now=2_000_000_000)


def test_client_acceptance_descriptor_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(lane.canonical_json_bytes(live_client_acceptance()))
    target.chmod(0o600)
    descriptor = tmp_path / "descriptor.json"
    descriptor.symlink_to(target)
    with pytest.raises(ValueError, match="absolute regular file"):
        lane.client_acceptance_descriptor(descriptor, now=2_000_000_000)


def test_client_acceptance_descriptor_rejects_unapproved_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = tmp_path / "descriptor.json"
    descriptor.write_bytes(lane.canonical_json_bytes(live_client_acceptance()))
    descriptor.chmod(0o600)
    real_stat = Path.stat

    def unowned_descriptor_stat(path: Path, *args, **kwargs):
        observed = real_stat(path, *args, **kwargs)
        if path == descriptor:
            fields = list(observed)
            fields[4] = os.getuid() + 1
            return os.stat_result(fields)
        return observed

    monkeypatch.setattr(Path, "stat", unowned_descriptor_stat)

    with pytest.raises(ValueError, match="private path has unsafe owner"):
        lane.client_acceptance_descriptor(descriptor, now=2_000_000_000)


def test_manifest_rejects_report_or_correlation_mutation_and_engine_substitution() -> (
    None
):
    cfg = config()
    cfg.update(
        {
            "engineIdentity": {
                "amneziawgGoCommit": "a" * 40,
                "amneziawgGoBinarySha256": "b" * 64,
            },
            "clientAcceptance": live_client_acceptance(),
        }
    )
    manifest = lane.run_lane(cfg, FakeExecutor(), metadata(), now=lambda: 2_000_000_000)
    for mutate in (
        lambda copy_: copy_["clientAcceptance"].update(reportSha256="0" * 64),
        lambda copy_: copy_["clientAcceptance"].update(correlationSha256="0" * 64),
        lambda copy_: copy_.update(clientAcceptance=copy_["engineIdentity"]),
    ):
        candidate = copy.deepcopy(manifest)
        mutate(candidate)
        with pytest.raises(ValueError):
            lane.validate_manifest(
                candidate, expected_source_sha="1" * 40, now=2_000_000_000
            )


def test_manifest_rejects_client_acceptance_outside_lane_window() -> None:
    cfg = config()
    cfg["clientAcceptance"] = live_client_acceptance(
        startedAtEpoch=1_999_998_000,
        finishedAtEpoch=1_999_998_100,
    )
    manifest = lane.run_lane(cfg, FakeExecutor(), metadata(), now=lambda: 2_000_000_000)

    with pytest.raises(ValueError, match="outside the run window"):
        lane.validate_manifest(
            manifest,
            expected_source_sha="1" * 40,
            now=2_000_000_000,
            max_age_seconds=10_000,
        )


def test_recurring_acceptance_requires_distinct_ordered_reports() -> None:
    cfg = config()
    cfg.update(
        {
            "engineIdentity": {
                "amneziawgGoCommit": "a" * 40,
                "amneziawgGoBinarySha256": "b" * 64,
            },
            "clientAcceptance": live_client_acceptance(),
        }
    )
    first = lane.run_lane(cfg, FakeExecutor(), metadata(), now=lambda: 2_000_000_000)
    later_acceptance = live_client_acceptance(
        reportSha256="1" * 64,
        startedAtEpoch=2_000_000_040,
        finishedAtEpoch=2_000_000_080,
    )
    later_cfg = {**cfg, "clientAcceptance": later_acceptance}
    later_metadata = {**metadata(), "invocationId": "43"}
    later = lane.run_lane(
        later_cfg, FakeExecutor(), later_metadata, now=lambda: 2_000_000_100
    )
    lane.validate_recurring_pair(first, later, now=2_000_000_100)

    replay = copy.deepcopy(later)
    replay["clientAcceptance"]["reportSha256"] = first["clientAcceptance"][
        "reportSha256"
    ]
    replay["clientAcceptance"]["correlationSha256"] = (
        lane.client_acceptance_correlation(replay["clientAcceptance"])
    )
    with pytest.raises(ValueError, match="distinct"):
        lane.validate_recurring_pair(first, replay, now=2_000_000_100)

    replay = copy.deepcopy(later)
    replay["clientAcceptance"]["correlationSha256"] = first["clientAcceptance"][
        "correlationSha256"
    ]
    with pytest.raises(ValueError, match="correlation"):
        lane.validate_recurring_pair(first, replay, now=2_000_000_100)

    for mutate, error in (
        (lambda copy_: copy_.update(sourceSha="3" * 40), "deploy source"),
        (
            lambda copy_: copy_["engineIdentity"].update(amneziawgGoCommit="4" * 40),
            "engine identity",
        ),
        (
            lambda copy_: copy_["clientAcceptance"].update(ripdpiSourceSha="5" * 40),
            "client ripdpiSourceSha",
        ),
        (
            lambda copy_: copy_["clientAcceptance"].update(apkSha256="6" * 64),
            "client apkSha256",
        ),
    ):
        mismatched = copy.deepcopy(later)
        mutate(mismatched)
        mismatched["clientAcceptance"]["correlationSha256"] = (
            lane.client_acceptance_correlation(mismatched["clientAcceptance"])
        )
        with pytest.raises(ValueError, match=error):
            lane.validate_recurring_pair(first, mismatched, now=2_000_000_100)


def test_recurring_pair_orders_embedded_client_acceptance_windows() -> None:
    first = recurring_manifest(1)
    later = recurring_manifest(2)
    later["clientAcceptance"].update(
        startedAtEpoch=1_999_999_900,
        finishedAtEpoch=1_999_999_920,
    )
    later["clientAcceptance"]["correlationSha256"] = lane.client_acceptance_correlation(
        later["clientAcceptance"]
    )

    with pytest.raises(ValueError, match="client acceptance is not ordered"):
        lane.validate_recurring_pair(first, later, now=2_000_000_300)


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

    loaded = lane.load_config(config_path, config_path.parent / CLIENT_ACCEPTANCE_NAME)

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
