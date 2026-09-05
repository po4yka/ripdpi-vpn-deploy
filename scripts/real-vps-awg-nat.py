#!/usr/bin/env python3
"""Run and validate the recurring real-VPS AmneziaWG/NAT evidence lane."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Protocol

CONFIG_VERSION = "real_vps_awg_nat_runner_v1"
MANIFEST_VERSION = "real_vps_awg_nat_evidence_v4"
CLIENT_ACCEPTANCE_FORMAT = "ripdpi_awg_live_acceptance_v1"
CLIENT_ACCEPTANCE_HANDOFF_FORMAT = "ripdpi_awg_live_acceptance_handoff_v1"
CLIENT_ACCEPTANCE_REQUEST_FORMAT = "ripdpi_awg_live_acceptance_request_v1"
WORKFLOW_PATH = ".github/workflows/real-vps-awg-nat.yml"
LOCAL_ENTRYPOINT_PATH = "scripts/run-real-vps-awg-nat-local.sh"
EXECUTOR_ENTRYPOINTS = {
    "github_actions": WORKFLOW_PATH,
    "local_systemd": LOCAL_ENTRYPOINT_PATH,
}
SHA1_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
INVOCATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
EXPECTED_PHASES = [
    "direct_control",
    "initial_connect",
    "restart_recovery",
    "old_key_rejection",
    "reload_rotation_recovery",
]
EXPECTED_OUTCOMES = {
    "direct_control": "success",
    "initial_connect": "success",
    "restart_recovery": "success",
    "old_key_rejection": "failure",
    "reload_rotation_recovery": "success",
}
CLASSIFICATIONS = {"PASS", "PRODUCT_FAILURE", "INFRA_UNAVAILABLE"}
REASON_CODES = {
    "NONE",
    "CONFIG_INVALID",
    "MISSING_CREDENTIALS",
    "PREREQUISITE_MISSING",
    "ECHO_CONTROL_UNAVAILABLE",
    "SERVER_CONTROL_UNAVAILABLE",
    "SERVER_SERVICE_UNHEALTHY",
    "AWG_START_FAILED",
    "AWG_ROUNDTRIP_FAILED",
    "HANDSHAKE_NOT_FRESH",
    "NAT_COUNTER_NOT_ADVANCED",
    "RESTART_FAILED",
    "ROTATION_FAILED",
    "RELOAD_FAILED",
    "DEPLOYMENT_MISMATCH",
    "DEPLOY_UNAVAILABLE",
    "DEPLOY_FAILED",
    "RESTART_NOT_OBSERVED",
    "RELOAD_NOT_OBSERVED",
    "OLD_KEY_STILL_ACCEPTED",
    "ROTATION_RECEIPT_INVALID",
    "ROLLBACK_FAILED",
    "COMMIT_FAILED",
    "INTERRUPTED",
    "CLEANUP_FAILED",
    "RUNNER_EXCEPTION",
    "PREFLIGHT_TOOL_MISSING",
    "PREFLIGHT_LOCK_BUSY",
    "PREFLIGHT_CONFIG_INVALID",
    "PREFLIGHT_RUNNER_INVALID",
    "PREFLIGHT_SOURCE_UNSAFE",
    "PREFLIGHT_SOURCE_MISMATCH",
}
CONFIG_FIELDS = {
    "version",
    "runnerId",
    "clientConfigPath",
    "rotatedClientConfigPath",
    "clientAddress",
    "tcpEchoAddress",
    "tcpEchoPort",
    "udpEchoAddress",
    "udpEchoPort",
    "serverControlHook",
    "serverDeployHook",
    "rotationHook",
    "probeTimeoutSeconds",
    "recoveryTimeoutSeconds",
    "deployTimeoutSeconds",
}
MANIFEST_FIELDS = {
    "version",
    "sourceSha",
    "engineIdentity",
    "clientAcceptance",
    "startedAtEpoch",
    "finishedAtEpoch",
    "generatedAtEpoch",
    "provenance",
    "runnerIdSha256",
    "producerDigests",
    "classification",
    "reasonCode",
    "phases",
    "captureDigests",
    "privateLogSha256",
    "serverDeployment",
    "rotation",
    "cleanup",
}
PROVENANCE_FIELDS = {
    "executor",
    "entrypointPath",
    "invocationId",
    "invocationAttempt",
    "sourceArchiveSha256",
}
ENGINE_IDENTITY_FIELDS = {"amneziawgGoCommit", "amneziawgGoBinarySha256"}
CLIENT_ACCEPTANCE_FIELDS = {
    "format",
    "ripdpiSourceSha",
    "apkSha256",
    "reportSha256",
    "correlationSha256",
    "startedAtEpoch",
    "finishedAtEpoch",
    "transport",
    "pass",
    "outcomes",
}
CLIENT_ACCEPTANCE_OUTCOME_FIELDS = {
    "routedTcp",
    "routedUdp",
    "recovery",
    "staleKeyRejected",
    "cleanup",
}
CLIENT_ACCEPTANCE_HANDOFF_FIELDS = {
    "format",
    "invocationId",
    "invocationAttempt",
    "nonce",
    "signatureAlgorithm",
    "signatureBase64",
    "acceptance",
}
CLIENT_ACCEPTANCE_REQUEST_FIELDS = {
    "format",
    "invocationId",
    "invocationAttempt",
    "nonce",
    "generatedAtEpoch",
    "expiresAtEpoch",
}
PRODUCER_FIELDS = {
    "runnerSha256",
    "serverControlHookSha256",
    "serverDeployHookSha256",
    "rotationHookSha256",
}
PHASE_FIELDS = {"id", "expected", "tcp", "udp", "server"}
PROBE_FIELDS = {"ok", "durationMs"}
SERVER_FIELDS = {
    "serviceActive",
    "interfaceUp",
    "deploymentCurrent",
    "peerConfigMatched",
    "handshakeFresh",
    "serviceGenerationChanged",
    "configGenerationChanged",
    "peerRxDelta",
    "peerTxDelta",
    "natPacketDelta",
    "natByteDelta",
}
STATUS_FIELDS = {
    "serviceActive",
    "interfaceUp",
    "deployedSourceSha",
    "deployedArchiveSha256",
    "serviceInvocationSha256",
    "configGenerationSha256",
    "peerConfigSha256",
    "latestHandshakeEpoch",
    "peerRxBytes",
    "peerTxBytes",
    "natPackets",
    "natBytes",
}
DEPLOYMENT_FIELDS = {"sourceCurrent", "archiveMatched", "receiptSha256"}
ROTATION_FIELDS = {
    "prepared",
    "oldKeyRejected",
    "newKeyMatched",
    "committed",
    "rolledBack",
}
CLEANUP_FIELDS = {
    "clientStopped",
    "capturesRemoved",
    "scratchRemoved",
    "serverTransactionFinalized",
}
DEPLOY_RECEIPT_FIELDS = {"deployedSourceSha", "deployedArchiveSha256"}
ROTATION_RECEIPT_FIELDS = {
    "previousConfigGenerationSha256",
    "nextConfigGenerationSha256",
    "previousPeerConfigSha256",
    "nextPeerConfigSha256",
    "rotatedClientConfigSha256",
}
FINALIZE_RECEIPT_FIELDS = {
    "action",
    "configGenerationSha256",
    "peerConfigSha256",
    "currentClientConfigSha256",
}


class Executor(Protocol):
    def deploy_source(self, source_sha: str, archive_sha256: str) -> dict[str, Any]:
        raise NotImplementedError

    def direct_probe(self) -> dict[str, Any]:
        raise NotImplementedError

    def server_status(self) -> dict[str, Any]:
        raise NotImplementedError

    def start_client(self, *, rotated: bool) -> None:
        raise NotImplementedError

    def probe(self, phase: str) -> dict[str, Any]:
        raise NotImplementedError

    def probe_once(self, phase: str) -> dict[str, Any]:
        raise NotImplementedError

    def server_action(self, action: str) -> None:
        raise NotImplementedError

    def stage_rotation(self) -> dict[str, Any]:
        raise NotImplementedError

    def finalize_rotation(self, action: str) -> dict[str, Any]:
        raise NotImplementedError

    def client_evidence(self, *, rotated: bool) -> dict[str, str]:
        raise NotImplementedError

    def stop_client(self) -> str:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class LaneFailure(RuntimeError):
    def __init__(self, classification: str, reason_code: str):
        super().__init__(reason_code)
        self.classification = classification
        self.reason_code = reason_code


class InfrastructureUnavailable(RuntimeError):
    """Private hook reported an environmental outage (sysexits EX_TEMPFAIL)."""


class HookProductFailure(RuntimeError):
    """Private hook reported a product defect (sysexits EX_SOFTWARE)."""


class MissingCredentials(RuntimeError):
    """Required AWG client credential material is absent or incomplete."""


class RecurringStateBusy(RuntimeError):
    """Another authorized executor owns the AWG evidence lane."""


class RecurringStateInterrupted(RuntimeError):
    """Test-only interruption after a durable recurring-state transition."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def require_fields(value: dict[str, Any], fields: set[str], context: str) -> None:
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ValueError(
            f"{context} fields differ; missing={missing}, unknown={unknown}"
        )


def require_sha(value: Any, pattern: re.Pattern[str], context: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{context} has invalid digest format")
    return value


def require_invocation_id(value: Any, context: str = "invocation id") -> str:
    if not isinstance(value, str) or INVOCATION_ID_RE.fullmatch(value) is None:
        raise ValueError(f"{context} has invalid format")
    return value


def _private_json_descriptor(
    path_value: Any, context: str, *, max_bytes: int = 4096
) -> dict[str, Any]:
    """Read a small private JSON descriptor through one inode-bound descriptor."""
    path = _secure_path(str(path_value), executable=False)
    expected = path.stat()
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_nlink != 1
            or observed.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(observed.st_mode) & 0o077
            or not 0 < observed.st_size <= max_bytes
            or (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise ValueError(f"{context} descriptor is unavailable")
        chunks = []
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ValueError(f"{context} descriptor is unavailable")
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except OSError as exc:
        raise ValueError(f"{context} descriptor is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not 0 < len(raw) <= max_bytes:
        raise ValueError(f"{context} descriptor is invalid")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{context} descriptor is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{context} descriptor is invalid")
    if raw != canonical_json_bytes(value):
        raise ValueError(f"{context} descriptor is not canonical JSON")
    return value


def client_acceptance_correlation(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "correlationSha256"}
    return sha256_bytes(canonical_json_bytes(payload))


def validate_client_acceptance(
    value: Any,
    *,
    now: int | None = None,
    max_age_seconds: int = 604800,
    require_pass: bool = True,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("client acceptance must be an object")
    require_fields(value, CLIENT_ACCEPTANCE_FIELDS, "client acceptance")
    if value["format"] != CLIENT_ACCEPTANCE_FORMAT:
        raise ValueError("client acceptance format is invalid")
    source_sha = require_sha(value["ripdpiSourceSha"], SHA1_RE, "client source SHA")
    apk_sha = require_sha(value["apkSha256"], SHA256_RE, "client APK SHA")
    report_sha = require_sha(value["reportSha256"], SHA256_RE, "client report SHA")
    require_sha(value["correlationSha256"], SHA256_RE, "client correlation SHA")
    if require_pass and (
        source_sha == "0" * 40 or apk_sha == "0" * 64 or report_sha == "0" * 64
    ):
        raise ValueError("client acceptance must bind a real source, APK, and report")
    if value["transport"] != "amneziawg":
        raise ValueError("client acceptance transport is invalid")
    started = require_int(value["startedAtEpoch"], "client acceptance timestamps", 1)
    finished = require_int(value["finishedAtEpoch"], "client acceptance timestamps", 1)
    if finished < started or finished - started > 3600:
        raise ValueError("client acceptance timestamps are inconsistent")
    current = int(time.time()) if now is None else now
    if require_pass and finished > current + 60:
        raise ValueError("client acceptance is from the future")
    if require_pass and current - finished > max_age_seconds:
        raise ValueError("client acceptance is stale")
    outcomes = value["outcomes"]
    if not isinstance(outcomes, dict):
        raise ValueError("client acceptance outcomes must be an object")
    require_fields(
        outcomes, CLIENT_ACCEPTANCE_OUTCOME_FIELDS, "client acceptance outcomes"
    )
    if not isinstance(value["pass"], bool) or not all(
        isinstance(outcomes[field], bool) for field in CLIENT_ACCEPTANCE_OUTCOME_FIELDS
    ):
        raise ValueError("client acceptance PASS outcomes must be boolean")
    if require_pass and (value["pass"] is not True or not all(outcomes.values())):
        raise ValueError("client acceptance PASS outcomes are incomplete")
    if value["correlationSha256"] != client_acceptance_correlation(value):
        raise ValueError("client acceptance correlation mismatch")
    return value


def client_acceptance_descriptor(
    path_value: Any, *, now: int | None = None, max_age_seconds: int = 604800
) -> dict[str, Any]:
    value = _private_json_descriptor(path_value, "client acceptance")
    return validate_client_acceptance(
        value, now=now, max_age_seconds=max_age_seconds, require_pass=True
    )


def client_acceptance_signature_payload(envelope: dict[str, Any]) -> bytes:
    """Return the canonical client-signed handoff bytes."""
    return canonical_json_bytes(
        {key: value for key, value in envelope.items() if key != "signatureBase64"}
    )


def _write_exact_private_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short private file write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validate_client_acceptance_handoff(
    value: Any,
    public_key_path: Path,
    *,
    expected_nonce: str,
    expected_invocation_id: str,
    expected_invocation_attempt: int = 1,
    now: int | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("client acceptance handoff must be an object")
    require_fields(value, CLIENT_ACCEPTANCE_HANDOFF_FIELDS, "client acceptance handoff")
    if value["format"] != CLIENT_ACCEPTANCE_HANDOFF_FORMAT:
        raise ValueError("client acceptance handoff format is invalid")
    if value["signatureAlgorithm"] != "ed25519":
        raise ValueError("client acceptance signature algorithm is invalid")
    nonce = require_sha(value["nonce"], SHA256_RE, "client acceptance nonce")
    if nonce == "0" * 64 or nonce != require_sha(
        expected_nonce, SHA256_RE, "expected client acceptance nonce"
    ):
        raise ValueError("client acceptance nonce mismatch")
    invocation_id = require_invocation_id(
        value["invocationId"], "client acceptance invocation id"
    )
    if invocation_id != require_invocation_id(expected_invocation_id):
        raise ValueError("client acceptance invocation mismatch")
    invocation_attempt = require_int(
        value["invocationAttempt"], "client acceptance invocation attempt", 1
    )
    if invocation_attempt != require_int(
        expected_invocation_attempt, "expected client acceptance invocation attempt", 1
    ):
        raise ValueError("client acceptance invocation attempt mismatch")
    try:
        signature = base64.b64decode(value["signatureBase64"], validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("client acceptance signature is invalid") from exc
    if len(signature) != 64:
        raise ValueError("client acceptance signature is invalid")
    public_key = _secure_path(str(public_key_path), executable=False)
    try:
        algorithm = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(public_key), "-text", "-noout"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(
            "client acceptance public key verification unavailable"
        ) from exc
    if (
        algorithm.returncode != 0
        or "ED25519 Public-Key:" not in algorithm.stdout.splitlines()
    ):
        raise ValueError("client acceptance public key is not Ed25519")
    with tempfile.TemporaryDirectory(prefix="ripdpi-awg-signature-") as temporary:
        temporary_path = Path(temporary)
        temporary_path.chmod(0o700)
        payload_path = temporary_path / "payload.json"
        signature_path = temporary_path / "signature.bin"
        _write_exact_private_file(
            payload_path, client_acceptance_signature_payload(value)
        )
        _write_exact_private_file(signature_path, signature)
        try:
            completed = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(public_key),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-sigfile",
                    str(signature_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                "client acceptance signature verification unavailable"
            ) from exc
    if completed.returncode != 0:
        raise ValueError("client acceptance signature verification failed")
    return validate_client_acceptance(value["acceptance"], now=now, require_pass=True)


def validate_client_acceptance_request(
    value: Any,
    *,
    expected_invocation_id: str,
    expected_invocation_attempt: int = 1,
    now: int | None = None,
) -> str:
    if not isinstance(value, dict):
        raise ValueError("client acceptance request must be an object")
    require_fields(value, CLIENT_ACCEPTANCE_REQUEST_FIELDS, "client acceptance request")
    if value["format"] != CLIENT_ACCEPTANCE_REQUEST_FORMAT:
        raise ValueError("client acceptance request format is invalid")
    invocation_id = require_invocation_id(
        value["invocationId"], "client acceptance request invocation id"
    )
    if invocation_id != require_invocation_id(expected_invocation_id):
        raise ValueError("client acceptance request invocation mismatch")
    invocation_attempt = require_int(
        value["invocationAttempt"], "client acceptance request invocation attempt", 1
    )
    if invocation_attempt != require_int(
        expected_invocation_attempt, "expected client acceptance invocation attempt", 1
    ):
        raise ValueError("client acceptance request invocation attempt mismatch")
    nonce = require_sha(value["nonce"], SHA256_RE, "client acceptance request nonce")
    if nonce == "0" * 64:
        raise ValueError("client acceptance request nonce is invalid")
    generated = require_int(
        value["generatedAtEpoch"], "client acceptance request generated timestamp", 1
    )
    expires = require_int(
        value["expiresAtEpoch"], "client acceptance request expiry timestamp", 1
    )
    if expires <= generated or expires - generated > 300:
        raise ValueError("client acceptance request lifetime is invalid")
    current = int(time.time()) if now is None else now
    if generated > current:
        raise ValueError("client acceptance request is from the future")
    if current > expires:
        raise ValueError("client acceptance request expired")
    return nonce


def _write_private_json_atomic(path: Path, value: Any) -> None:
    if not path.is_absolute() or path.parent.is_symlink():
        raise ValueError("client acceptance output directory is unsafe")
    try:
        parent = path.parent.resolve(strict=True)
        parent_info = parent.stat()
    except OSError as exc:
        raise ValueError("client acceptance output directory is unsafe") from exc
    if (
        not parent.is_dir()
        or parent_info.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(parent_info.st_mode) & 0o077
    ):
        raise ValueError("client acceptance output directory is unsafe")
    if path.exists() or path.is_symlink():
        raise ValueError("client acceptance output already exists")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        os.fchmod(descriptor, 0o600)
        payload = canonical_json_bytes(value)
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short client acceptance write")
            written += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def consume_client_acceptance_handoff(
    descriptor: Path,
    public_key: Path,
    *,
    request: Path,
    expected_invocation_id: str,
    expected_invocation_attempt: int = 1,
    output: Path,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify and consume one root-private, nonce-bound client handoff."""
    if output.exists() or output.is_symlink():
        raise ValueError("client acceptance output already exists")
    request_value = _private_json_descriptor(request, "client acceptance request")
    expected_nonce = validate_client_acceptance_request(
        request_value,
        expected_invocation_id=expected_invocation_id,
        expected_invocation_attempt=expected_invocation_attempt,
        now=now,
    )
    envelope = _private_json_descriptor(descriptor, "client acceptance handoff")
    acceptance = validate_client_acceptance_handoff(
        envelope,
        public_key,
        expected_nonce=expected_nonce,
        expected_invocation_id=expected_invocation_id,
        expected_invocation_attempt=expected_invocation_attempt,
        now=now,
    )
    consumed = descriptor.with_name(f".{descriptor.name}.consumed-{os.getpid()}")
    if consumed.exists() or consumed.is_symlink():
        raise ValueError("client acceptance consume path is unavailable")
    os.replace(descriptor, consumed)
    if (
        _private_json_descriptor(consumed, "consumed client acceptance handoff")
        != envelope
    ):
        raise ValueError("client acceptance handoff changed during consume")
    _write_private_json_atomic(output, acceptance)
    request.unlink()
    consumed.unlink()
    return acceptance


def create_client_acceptance_request(
    output: Path,
    invocation_id: str,
    *,
    invocation_attempt: int = 1,
    now: int | None = None,
    valid_seconds: int = 300,
) -> str:
    if not 1 <= valid_seconds <= 300:
        raise ValueError("client acceptance request lifetime is invalid")
    current = int(time.time()) if now is None else now
    nonce = secrets.token_hex(32)
    request = {
        "format": CLIENT_ACCEPTANCE_REQUEST_FORMAT,
        "invocationId": require_invocation_id(invocation_id),
        "invocationAttempt": require_int(
            invocation_attempt, "client acceptance request invocation attempt", 1
        ),
        "nonce": nonce,
        "generatedAtEpoch": current,
        "expiresAtEpoch": current + valid_seconds,
    }
    _write_private_json_atomic(output, request)
    return nonce


def validate_runtime_engine_identity(binary_path: Path) -> dict[str, str]:
    """Bind the engine identity to the immutable toolchain binary in use."""
    binary = _secure_path(str(binary_path), executable=True)
    if binary.name != "amneziawg-go":
        raise ValueError("client runtime binary is invalid")
    manifest_path = binary.parent.parent / "manifest.json"
    manifest_file = _secure_path(str(manifest_path), executable=False)
    raw = manifest_file.read_bytes()
    if not 0 < len(raw) <= 64 * 1024:
        raise ValueError("client runtime manifest is invalid")
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("client runtime manifest is invalid") from exc
    if raw != canonical_json_bytes(manifest) or not isinstance(manifest, dict):
        raise ValueError("client runtime manifest is invalid")
    require_fields(
        manifest,
        {"schemaVersion", "inputs", "binaries", "treeSha256"},
        "client runtime manifest",
    )
    if manifest["schemaVersion"] != 1:
        raise ValueError("client runtime manifest is invalid")
    inputs = manifest["inputs"]
    binaries = manifest["binaries"]
    if not isinstance(inputs, dict) or not isinstance(binaries, dict):
        raise ValueError("client runtime manifest is invalid")
    require_fields(
        inputs,
        {
            "goBundleSha256",
            "goCommit",
            "toolsBundleSha256",
            "toolsCommit",
            "vendorSha256",
        },
        "client runtime inputs",
    )
    require_fields(
        binaries,
        {"amneziawg-go", "awg", "awg-quick"},
        "client runtime binaries",
    )
    source_sha = require_sha(inputs["goCommit"], SHA1_RE, "client runtime source")
    artifact_sha256 = require_sha(
        binaries["amneziawg-go"], SHA256_RE, "client runtime artifact"
    )
    if sha256_bytes(binary.read_bytes()) != artifact_sha256:
        raise ValueError("client runtime artifact digest mismatch")
    return {
        "amneziawgGoCommit": source_sha,
        "amneziawgGoBinarySha256": artifact_sha256,
    }


def provenance_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "executor": metadata["executor"],
        "entrypointPath": metadata["entrypointPath"],
        "invocationId": metadata["invocationId"],
        "invocationAttempt": metadata["invocationAttempt"],
        "sourceArchiveSha256": metadata["sourceArchiveSha256"],
    }


def require_int(value: Any, context: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{context} must be an integer >= {minimum}")
    return value


def _probe_ok(probe: dict[str, Any]) -> bool:
    return all(probe.get(kind, {}).get("ok") is True for kind in ("tcp", "udp"))


def _probe_any_ok(probe: dict[str, Any]) -> bool:
    return any(probe.get(kind, {}).get("ok") is True for kind in ("tcp", "udp"))


def _phase(
    phase_id: str,
    probe: dict[str, Any],
    *,
    expected: str = "success",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    expected_source_sha: str | None = None,
    expected_archive_sha256: str | None = None,
    expected_peer_config_sha256: str | None = None,
    service_generation_changed: bool | None = None,
    config_generation_changed: bool | None = None,
) -> dict[str, Any]:
    server = None
    if before is not None and after is not None:
        server = {
            "serviceActive": after["serviceActive"],
            "interfaceUp": after["interfaceUp"],
            "deploymentCurrent": after["deployedSourceSha"] == expected_source_sha
            and after["deployedArchiveSha256"] == expected_archive_sha256,
            "peerConfigMatched": after["peerConfigSha256"]
            == expected_peer_config_sha256,
            "handshakeFresh": after["latestHandshakeEpoch"]
            > before["latestHandshakeEpoch"],
            "serviceGenerationChanged": (
                after["serviceInvocationSha256"] != before["serviceInvocationSha256"]
                if service_generation_changed is None
                else service_generation_changed
            ),
            "configGenerationChanged": (
                after["configGenerationSha256"] != before["configGenerationSha256"]
                if config_generation_changed is None
                else config_generation_changed
            ),
            "peerRxDelta": after["peerRxBytes"] - before["peerRxBytes"],
            "peerTxDelta": after["peerTxBytes"] - before["peerTxBytes"],
            "natPacketDelta": after["natPackets"] - before["natPackets"],
            "natByteDelta": after["natBytes"] - before["natBytes"],
        }
    return {
        "id": phase_id,
        "expected": expected,
        "tcp": probe["tcp"],
        "udp": probe["udp"],
        "server": server,
    }


def _server_phase_failure(phase: dict[str, Any]) -> str | None:
    server = phase["server"]
    if (
        not server["serviceActive"]
        or not server["interfaceUp"]
        or not server["deploymentCurrent"]
        or not server["peerConfigMatched"]
    ):
        return "SERVER_SERVICE_UNHEALTHY"
    deltas = (
        server["peerRxDelta"],
        server["peerTxDelta"],
        server["natPacketDelta"],
        server["natByteDelta"],
    )
    if phase["expected"] == "failure":
        if (
            _probe_any_ok(phase)
            or server["handshakeFresh"]
            or any(value != 0 for value in deltas)
        ):
            return "OLD_KEY_STILL_ACCEPTED"
    else:
        if not server["handshakeFresh"]:
            return "HANDSHAKE_NOT_FRESH"
        if any(value <= 0 for value in deltas):
            return "NAT_COUNTER_NOT_ADVANCED"
    return None


def run_lane(
    config: dict[str, Any],
    executor: Executor,
    metadata: dict[str, Any],
    *,
    now: Callable[[], int] = lambda: int(time.time()),
) -> dict[str, Any]:
    """Run the ordered lane through an injected real or test executor."""
    started = now()
    phases: list[dict[str, Any]] = []
    captures: list[str] = []
    classification = "PASS"
    reason_code = "NONE"
    client_active = False
    cleanup_ok = True
    scratch_removed = True
    server_transaction_finalized = True
    rotation_prepared = False
    rotation_committed = False
    rotation_rolled_back = False
    old_key_rejected = False
    new_key_matched = False
    rotation_receipt: dict[str, Any] | None = None
    rotation_baseline: dict[str, Any] | None = None
    previous_client_evidence: dict[str, str] | None = None
    deployment = {
        "sourceCurrent": False,
        "archiveMatched": False,
        "receiptSha256": "0" * 64,
    }
    private_log_fd, private_log_name = tempfile.mkstemp(prefix="ripdpi-awg-events-")
    private_log = Path(private_log_name)
    os.chmod(private_log, 0o600)

    def log_event(event: str, **fields: Any) -> None:
        record = {"event": event, "atEpoch": now(), **fields}
        os.write(private_log_fd, canonical_json_bytes(record))

    def stop_active_client() -> None:
        nonlocal client_active, cleanup_ok, classification, reason_code
        if not client_active:
            return
        try:
            captures.append(executor.stop_client())
            client_active = False
            log_event("client_stopped")
        except Exception:
            cleanup_ok = False
            classification = "INFRA_UNAVAILABLE"
            reason_code = "CLEANUP_FAILED"

    def read_client_evidence(*, rotated: bool) -> dict[str, str]:
        try:
            return executor.client_evidence(rotated=rotated)
        except MissingCredentials as exc:
            raise LaneFailure("INFRA_UNAVAILABLE", "MISSING_CREDENTIALS") from exc

    def read_server_status() -> dict[str, Any]:
        try:
            return executor.server_status()
        except InfrastructureUnavailable as exc:
            raise LaneFailure(
                "INFRA_UNAVAILABLE", "SERVER_CONTROL_UNAVAILABLE"
            ) from exc
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "SERVER_CONTROL_UNAVAILABLE") from exc

    def run_awg_phase(
        phase_id: str,
        before: dict[str, Any],
        expected_peer: str,
        *,
        service_generation_changed: bool | None = None,
        config_generation_changed: bool | None = None,
    ) -> dict[str, Any]:
        probe = executor.probe(phase_id)
        if not _probe_ok(probe):
            phases.append(_phase(phase_id, probe))
            raise LaneFailure("PRODUCT_FAILURE", "AWG_ROUNDTRIP_FAILED")
        after = read_server_status()
        phase = _phase(
            phase_id,
            probe,
            before=before,
            after=after,
            expected_source_sha=metadata["sourceSha"],
            expected_archive_sha256=metadata["sourceArchiveSha256"],
            expected_peer_config_sha256=expected_peer,
            service_generation_changed=service_generation_changed,
            config_generation_changed=config_generation_changed,
        )
        phases.append(phase)
        failure = _server_phase_failure(phase)
        if failure:
            raise LaneFailure("PRODUCT_FAILURE", failure)
        return after

    try:
        try:
            deploy_receipt = executor.deploy_source(
                metadata["sourceSha"], metadata["sourceArchiveSha256"]
            )
            require_fields(deploy_receipt, DEPLOY_RECEIPT_FIELDS, "deploy receipt")
        except InfrastructureUnavailable as exc:
            raise LaneFailure("INFRA_UNAVAILABLE", "DEPLOY_UNAVAILABLE") from exc
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "DEPLOY_FAILED") from exc
        deployment = {
            "sourceCurrent": deploy_receipt["deployedSourceSha"]
            == metadata["sourceSha"],
            "archiveMatched": deploy_receipt["deployedArchiveSha256"]
            == metadata["sourceArchiveSha256"],
            "receiptSha256": sha256_bytes(canonical_json_bytes(deploy_receipt)),
        }
        if not deployment["sourceCurrent"] or not deployment["archiveMatched"]:
            raise LaneFailure("PRODUCT_FAILURE", "DEPLOYMENT_MISMATCH")
        log_event("source_deployed", receiptSha256=deployment["receiptSha256"])

        current_client = read_client_evidence(rotated=False)
        direct = executor.direct_probe()
        phases.append(_phase("direct_control", direct))
        if not _probe_ok(direct):
            raise LaneFailure("INFRA_UNAVAILABLE", "ECHO_CONTROL_UNAVAILABLE")
        status = read_server_status()
        if not status["serviceActive"] or not status["interfaceUp"]:
            raise LaneFailure("PRODUCT_FAILURE", "SERVER_SERVICE_UNHEALTHY")
        if (
            status["deployedSourceSha"] != metadata["sourceSha"]
            or status["deployedArchiveSha256"] != metadata["sourceArchiveSha256"]
        ):
            raise LaneFailure("PRODUCT_FAILURE", "DEPLOYMENT_MISMATCH")
        if status["peerConfigSha256"] != current_client["peerConfigSha256"]:
            raise LaneFailure("INFRA_UNAVAILABLE", "ROTATION_RECEIPT_INVALID")

        try:
            executor.start_client(rotated=False)
            client_active = True
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "AWG_START_FAILED") from exc
        status = run_awg_phase(
            "initial_connect", status, current_client["peerConfigSha256"]
        )

        try:
            executor.server_action("restart")
        except InfrastructureUnavailable as exc:
            raise LaneFailure(
                "INFRA_UNAVAILABLE", "SERVER_CONTROL_UNAVAILABLE"
            ) from exc
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "RESTART_FAILED") from exc
        before_restart = status
        status = read_server_status()
        restart_observed = (
            before_restart["serviceInvocationSha256"]
            != status["serviceInvocationSha256"]
            and before_restart["configGenerationSha256"]
            == status["configGenerationSha256"]
        )
        if not restart_observed:
            raise LaneFailure("PRODUCT_FAILURE", "RESTART_NOT_OBSERVED")
        status = run_awg_phase(
            "restart_recovery",
            status,
            current_client["peerConfigSha256"],
            service_generation_changed=True,
            config_generation_changed=False,
        )
        stop_active_client()
        if not cleanup_ok:
            raise LaneFailure(classification, reason_code)

        try:
            rotation_baseline = dict(status)
            previous_client_evidence = dict(current_client)
            rotation_prepared = True
            server_transaction_finalized = False
            rotation_receipt = executor.stage_rotation()
            require_fields(
                rotation_receipt, ROTATION_RECEIPT_FIELDS, "rotation receipt"
            )
            for key, value in rotation_receipt.items():
                require_sha(value, SHA256_RE, f"rotation receipt {key}")
            rotated_client = read_client_evidence(rotated=True)
            if (
                rotation_receipt["previousConfigGenerationSha256"]
                != status["configGenerationSha256"]
                or rotation_receipt["previousPeerConfigSha256"]
                != current_client["peerConfigSha256"]
                or rotation_receipt["nextConfigGenerationSha256"]
                == status["configGenerationSha256"]
                or rotation_receipt["nextPeerConfigSha256"]
                == current_client["peerConfigSha256"]
                or rotation_receipt["nextPeerConfigSha256"]
                != rotated_client["peerConfigSha256"]
                or rotation_receipt["rotatedClientConfigSha256"]
                != rotated_client["clientConfigSha256"]
            ):
                raise LaneFailure("PRODUCT_FAILURE", "ROTATION_RECEIPT_INVALID")
            log_event("rotation_prepared")
        except InfrastructureUnavailable as exc:
            raise LaneFailure(
                "INFRA_UNAVAILABLE", "SERVER_CONTROL_UNAVAILABLE"
            ) from exc
        except LaneFailure:
            raise
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "ROTATION_FAILED") from exc
        try:
            executor.server_action("reload")
        except InfrastructureUnavailable as exc:
            raise LaneFailure(
                "INFRA_UNAVAILABLE", "SERVER_CONTROL_UNAVAILABLE"
            ) from exc
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "RELOAD_FAILED") from exc
        before_reload = status
        status = read_server_status()
        reload_observed = (
            status["configGenerationSha256"]
            == rotation_receipt["nextConfigGenerationSha256"]
            and status["configGenerationSha256"]
            != before_reload["configGenerationSha256"]
            and status["peerConfigSha256"] == rotation_receipt["nextPeerConfigSha256"]
        )
        if not reload_observed:
            raise LaneFailure("PRODUCT_FAILURE", "RELOAD_NOT_OBSERVED")
        try:
            executor.start_client(rotated=False)
            client_active = True
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "AWG_START_FAILED") from exc
        negative_probe = executor.probe_once("old_key_rejection")
        after_negative = read_server_status()
        negative_phase = _phase(
            "old_key_rejection",
            negative_probe,
            expected="failure",
            before=status,
            after=after_negative,
            expected_source_sha=metadata["sourceSha"],
            expected_archive_sha256=metadata["sourceArchiveSha256"],
            expected_peer_config_sha256=rotation_receipt["nextPeerConfigSha256"],
            service_generation_changed=False,
            config_generation_changed=True,
        )
        phases.append(negative_phase)
        negative_failure = _server_phase_failure(negative_phase)
        if negative_failure:
            raise LaneFailure("PRODUCT_FAILURE", negative_failure)
        if (
            not negative_phase["server"]["configGenerationChanged"]
            or after_negative["configGenerationSha256"]
            != rotation_receipt["nextConfigGenerationSha256"]
        ):
            raise LaneFailure("PRODUCT_FAILURE", "RELOAD_NOT_OBSERVED")
        old_key_rejected = True
        stop_active_client()
        if not cleanup_ok:
            raise LaneFailure(classification, reason_code)
        try:
            executor.start_client(rotated=True)
            client_active = True
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "AWG_START_FAILED") from exc
        run_awg_phase(
            "reload_rotation_recovery",
            after_negative,
            rotation_receipt["nextPeerConfigSha256"],
            service_generation_changed=False,
            config_generation_changed=False,
        )
        new_key_matched = True
        stop_active_client()
        if not cleanup_ok:
            raise LaneFailure(classification, reason_code)
        try:
            commit_receipt = executor.finalize_rotation("commit")
            require_fields(commit_receipt, FINALIZE_RECEIPT_FIELDS, "commit receipt")
            current_after_commit = read_client_evidence(rotated=False)
            if (
                commit_receipt["action"] != "commit"
                or commit_receipt["configGenerationSha256"]
                != rotation_receipt["nextConfigGenerationSha256"]
                or commit_receipt["peerConfigSha256"]
                != rotation_receipt["nextPeerConfigSha256"]
                or commit_receipt["currentClientConfigSha256"]
                != current_after_commit["clientConfigSha256"]
                or current_after_commit != rotated_client
            ):
                raise ValueError("commit receipt does not promote rotated client")
            rotation_committed = True
            server_transaction_finalized = True
            log_event("rotation_committed")
        except LaneFailure:
            raise
        except InfrastructureUnavailable as exc:
            raise LaneFailure("INFRA_UNAVAILABLE", "COMMIT_FAILED") from exc
        except Exception as exc:
            raise LaneFailure("PRODUCT_FAILURE", "COMMIT_FAILED") from exc
    except LaneFailure as exc:
        classification = exc.classification
        reason_code = exc.reason_code
    except Exception:
        classification = "INFRA_UNAVAILABLE"
        reason_code = "RUNNER_EXCEPTION"
    finally:
        stop_active_client()
        if rotation_prepared and not rotation_committed:
            try:
                rollback_receipt = executor.finalize_rotation("rollback")
                require_fields(
                    rollback_receipt, FINALIZE_RECEIPT_FIELDS, "rollback receipt"
                )
                if (
                    rollback_receipt["action"] != "rollback"
                    or rotation_baseline is None
                    or previous_client_evidence is None
                    or rollback_receipt["configGenerationSha256"]
                    != rotation_baseline["configGenerationSha256"]
                    or rollback_receipt["peerConfigSha256"]
                    != rotation_baseline["peerConfigSha256"]
                    or rollback_receipt["currentClientConfigSha256"]
                    != previous_client_evidence["clientConfigSha256"]
                ):
                    raise ValueError("rollback receipt mismatch")
                executor.server_action("reload")
                restored = executor.server_status()
                if (
                    restored["configGenerationSha256"]
                    != rotation_baseline["configGenerationSha256"]
                    or restored["peerConfigSha256"]
                    != rotation_baseline["peerConfigSha256"]
                ):
                    raise ValueError("server rollback was not observed")
                executor.start_client(rotated=False)
                client_active = True
                recovery = executor.probe("rollback_recovery")
                if not _probe_ok(recovery):
                    raise ValueError("old client did not recover after rollback")
                stop_active_client()
                rotation_rolled_back = True
                server_transaction_finalized = True
                log_event("rotation_rolled_back")
            except InfrastructureUnavailable:
                classification = "INFRA_UNAVAILABLE"
                reason_code = "ROLLBACK_FAILED"
                server_transaction_finalized = False
                cleanup_ok = False
                stop_active_client()
            except Exception:
                classification = "PRODUCT_FAILURE"
                reason_code = "ROLLBACK_FAILED"
                server_transaction_finalized = False
                cleanup_ok = False
                stop_active_client()
        try:
            executor.close()
        except Exception:
            classification = "INFRA_UNAVAILABLE"
            reason_code = "CLEANUP_FAILED"
            cleanup_ok = False
            scratch_removed = False

    try:
        log_event(
            "lane_finished", classification=classification, reasonCode=reason_code
        )
        os.close(private_log_fd)
        private_log_sha256 = sha256_bytes(private_log.read_bytes())
        private_log.unlink()
    except OSError:
        classification = "INFRA_UNAVAILABLE"
        reason_code = "CLEANUP_FAILED"
        cleanup_ok = False
        scratch_removed = False
        private_log_sha256 = "0" * 64

    finished = now()
    return {
        "version": MANIFEST_VERSION,
        "sourceSha": metadata["sourceSha"],
        "engineIdentity": config["engineIdentity"],
        "clientAcceptance": config["clientAcceptance"],
        "startedAtEpoch": started,
        "finishedAtEpoch": finished,
        "generatedAtEpoch": finished,
        "provenance": provenance_from_metadata(metadata),
        "runnerIdSha256": config["runnerIdSha256"],
        "producerDigests": {
            "runnerSha256": config["producerSha256"],
            "serverControlHookSha256": config["serverControlHookSha256"],
            "serverDeployHookSha256": config["serverDeployHookSha256"],
            "rotationHookSha256": config["rotationHookSha256"],
        },
        "classification": classification,
        "reasonCode": reason_code,
        "phases": phases,
        "captureDigests": captures,
        "privateLogSha256": private_log_sha256,
        "serverDeployment": deployment,
        "rotation": {
            "prepared": rotation_prepared,
            "oldKeyRejected": old_key_rejected,
            "newKeyMatched": new_key_matched,
            "committed": rotation_committed,
            "rolledBack": rotation_rolled_back,
        },
        "cleanup": {
            "clientStopped": not client_active,
            "capturesRemoved": cleanup_ok,
            "scratchRemoved": scratch_removed,
            "serverTransactionFinalized": server_transaction_finalized,
        },
    }


def _validate_probe(value: Any, context: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    require_fields(value, PROBE_FIELDS, context)
    if not isinstance(value["ok"], bool):
        raise ValueError(f"{context}.ok must be boolean")
    duration = value["durationMs"]
    if value["ok"]:
        require_int(duration, f"{context}.durationMs")
    elif duration is not None:
        raise ValueError(f"{context}.durationMs must be null on failure")


def validate_manifest(
    manifest: Any,
    *,
    expected_source_sha: str,
    now: int | None = None,
    max_age_seconds: int = 604800,
    expected_executor: str | None = None,
    expected_invocation_id: str | None = None,
    expected_invocation_attempt: int | None = None,
    expected_source_archive_sha256: str | None = None,
    expected_engine_commit: str | None = None,
    expected_engine_binary_sha256: str | None = None,
    expected_client_source_sha: str | None = None,
    expected_client_apk_sha256: str | None = None,
    expected_client_report_sha256: str | None = None,
    expected_client_correlation_sha256: str | None = None,
) -> None:
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    require_fields(manifest, MANIFEST_FIELDS, "manifest")
    if manifest["version"] != MANIFEST_VERSION:
        raise ValueError("unsupported manifest version")
    require_sha(expected_source_sha, SHA1_RE, "expected source SHA")
    if manifest["sourceSha"] != expected_source_sha:
        raise ValueError("manifest source SHA mismatch")
    engine_identity = manifest["engineIdentity"]
    if not isinstance(engine_identity, dict):
        raise ValueError("engine identity must be an object")
    require_fields(engine_identity, ENGINE_IDENTITY_FIELDS, "engine identity")
    require_sha(engine_identity["amneziawgGoCommit"], SHA1_RE, "engine commit")
    require_sha(
        engine_identity["amneziawgGoBinarySha256"], SHA256_RE, "engine binary SHA"
    )
    if expected_engine_commit is not None and (
        engine_identity["amneziawgGoCommit"]
        != require_sha(expected_engine_commit, SHA1_RE, "expected engine commit")
    ):
        raise ValueError("manifest engine commit mismatch")
    if expected_engine_binary_sha256 is not None and (
        engine_identity["amneziawgGoBinarySha256"]
        != require_sha(
            expected_engine_binary_sha256, SHA256_RE, "expected engine binary SHA"
        )
    ):
        raise ValueError("manifest engine binary SHA mismatch")
    client_acceptance = validate_client_acceptance(
        manifest["clientAcceptance"],
        now=now,
        max_age_seconds=max_age_seconds,
        require_pass=manifest.get("classification") == "PASS",
    )
    if expected_client_source_sha is not None:
        require_sha(expected_client_source_sha, SHA1_RE, "expected client source SHA")
        if client_acceptance["ripdpiSourceSha"] != expected_client_source_sha:
            raise ValueError("manifest client source SHA mismatch")
    if expected_client_apk_sha256 is not None:
        require_sha(
            expected_client_apk_sha256,
            SHA256_RE,
            "expected client APK SHA",
        )
        if client_acceptance["apkSha256"] != expected_client_apk_sha256:
            raise ValueError("manifest client APK SHA mismatch")
    for key, expected, label in (
        ("reportSha256", expected_client_report_sha256, "report"),
        ("correlationSha256", expected_client_correlation_sha256, "correlation"),
    ):
        if expected is not None and client_acceptance[key] != require_sha(
            expected, SHA256_RE, f"expected client {label} SHA"
        ):
            raise ValueError(f"manifest client {label} SHA mismatch")
    started = require_int(manifest["startedAtEpoch"], "startedAtEpoch", 1)
    finished = require_int(manifest["finishedAtEpoch"], "finishedAtEpoch", 1)
    generated = require_int(manifest["generatedAtEpoch"], "generatedAtEpoch", 1)
    if finished < started or generated != finished:
        raise ValueError("manifest timestamps are inconsistent")
    if manifest.get("classification") == "PASS" and (
        client_acceptance["finishedAtEpoch"] < started - 900
        or client_acceptance["startedAtEpoch"] > finished + 60
    ):
        raise ValueError("client acceptance is outside the run window")
    current = int(time.time()) if now is None else now
    if generated > current + 60:
        raise ValueError("manifest is from the future")
    if current - generated > max_age_seconds:
        raise ValueError("manifest is stale")
    provenance = manifest["provenance"]
    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object")
    require_fields(provenance, PROVENANCE_FIELDS, "provenance")
    executor = provenance["executor"]
    if executor not in EXECUTOR_ENTRYPOINTS:
        raise ValueError("provenance executor is invalid")
    if provenance["entrypointPath"] != EXECUTOR_ENTRYPOINTS[executor]:
        raise ValueError("provenance entrypoint mismatch")
    if expected_executor is not None and executor != expected_executor:
        raise ValueError("manifest executor mismatch")
    require_sha(
        provenance["sourceArchiveSha256"],
        SHA256_RE,
        "provenance source archive",
    )
    if expected_source_archive_sha256 is not None:
        require_sha(
            expected_source_archive_sha256,
            SHA256_RE,
            "expected source archive",
        )
        if provenance["sourceArchiveSha256"] != expected_source_archive_sha256:
            raise ValueError("manifest source archive SHA mismatch")
    invocation_id = require_invocation_id(provenance["invocationId"])
    invocation_attempt = require_int(
        provenance["invocationAttempt"], "invocationAttempt", 1
    )
    if expected_invocation_id is not None and invocation_id != require_invocation_id(
        expected_invocation_id
    ):
        raise ValueError("invocation id mismatch")
    if (
        expected_invocation_attempt is not None
        and invocation_attempt != expected_invocation_attempt
    ):
        raise ValueError("invocation attempt mismatch")
    require_sha(manifest["runnerIdSha256"], SHA256_RE, "runner id")
    producers = manifest["producerDigests"]
    if not isinstance(producers, dict):
        raise ValueError("producerDigests must be an object")
    require_fields(producers, PRODUCER_FIELDS, "producerDigests")
    for key, value in producers.items():
        require_sha(value, SHA256_RE, f"producerDigests.{key}")
    classification = manifest["classification"]
    reason_code = manifest["reasonCode"]
    if classification not in CLASSIFICATIONS or reason_code not in REASON_CODES:
        raise ValueError("manifest classification is invalid")
    phases = manifest["phases"]
    if not isinstance(phases, list):
        raise ValueError("phases must be an array")
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise ValueError("phase must be an object")
        require_fields(phase, PHASE_FIELDS, f"phases[{index}]")
        if phase["expected"] not in {"success", "failure"}:
            raise ValueError("phase expected outcome is invalid")
        _validate_probe(phase["tcp"], f"phases[{index}].tcp")
        _validate_probe(phase["udp"], f"phases[{index}].udp")
        if phase["id"] == "direct_control":
            if phase["server"] is not None:
                raise ValueError("direct control must not include server counters")
        elif phase["server"] is not None:
            server = phase["server"]
            if not isinstance(server, dict):
                raise ValueError("server evidence must be an object")
            require_fields(server, SERVER_FIELDS, f"phases[{index}].server")
            if not all(
                isinstance(server[key], bool)
                for key in (
                    "serviceActive",
                    "interfaceUp",
                    "deploymentCurrent",
                    "peerConfigMatched",
                    "handshakeFresh",
                    "serviceGenerationChanged",
                    "configGenerationChanged",
                )
            ):
                raise ValueError("server state fields must be boolean")
            for key in (
                "peerRxDelta",
                "peerTxDelta",
                "natPacketDelta",
                "natByteDelta",
            ):
                require_int(server[key], key)
    captures = manifest["captureDigests"]
    if not isinstance(captures, list):
        raise ValueError("captureDigests must be an array")
    for digest in captures:
        require_sha(digest, SHA256_RE, "capture digest")
    require_sha(manifest["privateLogSha256"], SHA256_RE, "private log digest")
    deployment = manifest["serverDeployment"]
    if not isinstance(deployment, dict):
        raise ValueError("serverDeployment must be an object")
    require_fields(deployment, DEPLOYMENT_FIELDS, "serverDeployment")
    if not all(
        isinstance(deployment[key], bool) for key in ("sourceCurrent", "archiveMatched")
    ):
        raise ValueError("server deployment flags must be boolean")
    require_sha(deployment["receiptSha256"], SHA256_RE, "deployment receipt")
    rotation = manifest["rotation"]
    if not isinstance(rotation, dict):
        raise ValueError("rotation must be an object")
    require_fields(rotation, ROTATION_FIELDS, "rotation")
    if not all(isinstance(value, bool) for value in rotation.values()):
        raise ValueError("rotation flags must be boolean")
    cleanup = manifest["cleanup"]
    if not isinstance(cleanup, dict):
        raise ValueError("cleanup must be an object")
    require_fields(cleanup, CLEANUP_FIELDS, "cleanup")
    if not all(value is True for value in cleanup.values()):
        raise ValueError("cleanup evidence is incomplete")
    if classification == "PASS":
        pass_digests = [
            manifest["sourceSha"],
            provenance["sourceArchiveSha256"],
            manifest["runnerIdSha256"],
            *producers.values(),
            *captures,
            manifest["privateLogSha256"],
            deployment["receiptSha256"],
        ]
        if any(set(digest) == {"0"} for digest in pass_digests):
            raise ValueError("PASS manifest contains a placeholder digest")
        if (
            engine_identity["amneziawgGoCommit"] == "0" * 40
            or engine_identity["amneziawgGoBinarySha256"] == "0" * 64
        ):
            raise ValueError("PASS manifest lacks engine identity")
        if (
            reason_code != "NONE"
            or [phase["id"] for phase in phases] != EXPECTED_PHASES
        ):
            raise ValueError("PASS manifest lacks the complete phase sequence")
        if any(phase["expected"] != EXPECTED_OUTCOMES[phase["id"]] for phase in phases):
            raise ValueError("PASS manifest has an invalid phase outcome contract")
        if len(captures) != 3 or len(set(captures)) != 3:
            raise ValueError("PASS manifest must bind three distinct captures")
        if (
            deployment["sourceCurrent"] is not True
            or deployment["archiveMatched"] is not True
        ):
            raise ValueError("PASS manifest is not tied to the deployed source")
        if rotation != {
            "prepared": True,
            "oldKeyRejected": True,
            "newKeyMatched": True,
            "committed": True,
            "rolledBack": False,
        }:
            raise ValueError("PASS manifest lacks transactional rotation evidence")
        for phase in phases:
            if phase["expected"] == "success" and not _probe_ok(phase):
                raise ValueError("PASS manifest contains a failed roundtrip")
            if phase["expected"] == "failure" and _probe_any_ok(phase):
                raise ValueError("PASS manifest accepted the old key")
            if phase["id"] != "direct_control":
                if _server_phase_failure(phase):
                    raise ValueError("PASS manifest contains invalid server evidence")
        if phases[2]["server"]["serviceGenerationChanged"] is not True:
            raise ValueError("PASS manifest did not observe service restart")
        if phases[3]["server"]["configGenerationChanged"] is not True:
            raise ValueError("PASS manifest did not observe config reload")
    elif reason_code == "NONE":
        raise ValueError("non-PASS manifest requires a reason code")


def validate_recurring_pair(
    initial: Any,
    recurring: Any,
    *,
    now: int | None = None,
    max_age_seconds: int = 604800,
) -> None:
    """Require two complete, ordered and independently correlated PASS runs."""
    if not isinstance(initial, dict) or not isinstance(recurring, dict):
        raise ValueError("recurring evidence must contain two manifests")
    validate_manifest(
        initial,
        expected_source_sha=initial.get("sourceSha", ""),
        now=now,
        max_age_seconds=max_age_seconds,
    )
    validate_manifest(
        recurring,
        expected_source_sha=recurring.get("sourceSha", ""),
        now=now,
        max_age_seconds=max_age_seconds,
    )
    if initial["classification"] != "PASS" or recurring["classification"] != "PASS":
        raise ValueError("recurring evidence requires PASS manifests")
    if initial["sourceSha"] != recurring["sourceSha"]:
        raise ValueError("recurring deploy source must remain exact")
    if initial["engineIdentity"] != recurring["engineIdentity"]:
        raise ValueError("recurring engine identity must remain exact")
    for field in ("ripdpiSourceSha", "apkSha256"):
        if initial["clientAcceptance"][field] != recurring["clientAcceptance"][field]:
            raise ValueError(f"recurring client {field} must remain exact")
    if initial["finishedAtEpoch"] >= recurring["startedAtEpoch"]:
        raise ValueError("recurring evidence is not ordered")
    if (
        initial["provenance"]["invocationId"],
        initial["provenance"]["invocationAttempt"],
    ) == (
        recurring["provenance"]["invocationId"],
        recurring["provenance"]["invocationAttempt"],
    ):
        raise ValueError("recurring evidence invocation must be distinct")
    for field in ("reportSha256", "correlationSha256"):
        if initial["clientAcceptance"][field] == recurring["clientAcceptance"][field]:
            raise ValueError(f"recurring client {field} must be distinct")


def _read_state_manifest(path: Path, *, now: int | None = None) -> dict[str, Any]:
    value = _private_json_descriptor(str(path), "recurring evidence", max_bytes=262144)
    validate_manifest(value, expected_source_sha=value.get("sourceSha", ""), now=now)
    if value["classification"] != "PASS":
        raise ValueError("recurring state requires PASS evidence")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_state_manifest(
    state_dir: Path,
    name: str,
    manifest: dict[str, Any],
    *,
    failpoint: str | None = None,
) -> None:
    target = state_dir / name
    temporary = state_dir / f".{name}.tmp"
    payload = canonical_json_bytes(manifest)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short recurring state write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if failpoint == f"after-{name.removesuffix('.json')}-temp-fsync":
        raise RecurringStateInterrupted(failpoint)
    os.replace(temporary, target)
    _fsync_directory(state_dir)
    if failpoint == f"after-{name.removesuffix('.json')}-replace":
        raise RecurringStateInterrupted(failpoint)


def _unlink_state(path: Path) -> None:
    path.unlink()
    _fsync_directory(path.parent)


def _state_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _recover_state_temporary(path: Path, *, now: int | None) -> dict[str, Any] | None:
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_nlink != 1
        or observed.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(observed.st_mode) != 0o600
        or observed.st_size > 262144
    ):
        raise ValueError("recurring state recovery file has unsafe metadata")
    try:
        return _read_state_manifest(path, now=now)
    except (OSError, ValueError, json.JSONDecodeError):
        # The fixed private temporary name is owned exclusively under the lane
        # lock. A truncated pre-rename write is not evidence and is discarded.
        _unlink_state(path)
        return None


def _acquire_recurring_lock(lock_path: Path, lock_fd: int | None) -> tuple[int, bool]:
    opened = lock_fd is None
    descriptor = (
        os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        if opened
        else lock_fd
    )
    assert descriptor is not None
    try:
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_nlink != 1
            or observed.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(observed.st_mode) != 0o600
        ):
            raise ValueError("recurring lane lock has unsafe metadata")
        named = os.stat(lock_path, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (observed.st_dev, observed.st_ino):
            raise ValueError("recurring lane lock identity changed")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        if opened:
            os.close(descriptor)
        raise RecurringStateBusy("recurring lane lock is busy") from exc
    except Exception:
        if opened:
            os.close(descriptor)
        raise
    return descriptor, opened


def record_recurring_state(
    current: dict[str, Any],
    state_dir: Path,
    *,
    lock_path: Path,
    lock_fd: int | None = None,
    now: int | None = None,
    failpoint: str | None = None,
    expected: dict[str, Any] | None = None,
) -> str:
    """Validate and durably advance initial/recurring PASS evidence."""
    descriptor, opened = _acquire_recurring_lock(lock_path, lock_fd)
    pending_path = state_dir / "pending-initial.json"
    latest_path = state_dir / "latest.json"
    try:
        validation = dict(expected or {})
        validation.setdefault("expected_source_sha", current.get("sourceSha", ""))
        validate_manifest(current, now=now, **validation)
        if current["classification"] != "PASS":
            raise ValueError("recurring state requires PASS evidence")
        state_info = state_dir.lstat()
        if (
            not stat.S_ISDIR(state_info.st_mode)
            or state_info.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(state_info.st_mode) != 0o700
        ):
            raise ValueError("recurring state directory has unsafe metadata")
        pending_tmp = state_dir / ".pending-initial.json.tmp"
        latest_tmp = state_dir / ".latest.json.tmp"
        if _state_entry_exists(pending_tmp):
            recovered = _recover_state_temporary(pending_tmp, now=now)
            if recovered is not None:
                if _state_entry_exists(pending_path) or _state_entry_exists(
                    latest_path
                ):
                    raise ValueError("ambiguous pending state recovery")
                os.replace(pending_tmp, pending_path)
                _fsync_directory(state_dir)
        if _state_entry_exists(latest_tmp):
            recovered = _recover_state_temporary(latest_tmp, now=now)
            if recovered is not None:
                prior_path = (
                    latest_path if _state_entry_exists(latest_path) else pending_path
                )
                if not _state_entry_exists(prior_path):
                    raise ValueError("ambiguous latest state recovery")
                prior = _read_state_manifest(prior_path, now=now)
                validate_recurring_pair(prior, recovered, now=now)
                os.replace(latest_tmp, latest_path)
                _fsync_directory(state_dir)
        pending = (
            _read_state_manifest(pending_path, now=now)
            if _state_entry_exists(pending_path)
            else None
        )
        latest = (
            _read_state_manifest(latest_path, now=now)
            if _state_entry_exists(latest_path)
            else None
        )
        if pending is not None and latest is not None:
            validate_recurring_pair(pending, latest, now=now)
            _unlink_state(pending_path)
            pending = None
        if latest is not None:
            if canonical_json_bytes(latest) == canonical_json_bytes(current):
                return "published"
            validate_recurring_pair(latest, current, now=now)
            _atomic_state_manifest(
                state_dir, "latest.json", current, failpoint=failpoint
            )
            return "published"
        if pending is not None:
            if canonical_json_bytes(pending) == canonical_json_bytes(current):
                return "pending"
            validate_recurring_pair(pending, current, now=now)
            _atomic_state_manifest(
                state_dir, "latest.json", current, failpoint=failpoint
            )
            _unlink_state(pending_path)
            return "published"
        _atomic_state_manifest(
            state_dir, "pending-initial.json", current, failpoint=failpoint
        )
        return "pending"
    finally:
        if opened:
            os.close(descriptor)


def record_recurring_manifest_path(
    manifest_path: Path,
    state_dir: Path,
    *,
    lock_path: Path,
    lock_fd: int | None = None,
    expected: dict[str, Any],
) -> str:
    """Read and publish the current manifest while holding the host-lane lock."""
    descriptor, opened = _acquire_recurring_lock(lock_path, lock_fd)
    try:
        current = _private_json_descriptor(
            manifest_path, "current evidence", max_bytes=262144
        )
        return record_recurring_state(
            current,
            state_dir,
            lock_path=lock_path,
            lock_fd=descriptor,
            expected=expected,
        )
    finally:
        if opened:
            os.close(descriptor)


def _secure_path(path_value: Any, *, executable: bool) -> Path:
    if not isinstance(path_value, str):
        raise ValueError("private path must be a string")
    candidate = Path(path_value)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ValueError("private path must be an absolute regular file")
    try:
        path = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("private path must be an absolute regular file") from exc
    if not path.is_file():
        raise ValueError("private path must be an absolute regular file")
    allowed_owners = {0, os.geteuid()}
    for parent in path.parents:
        info = parent.stat()
        mode = stat.S_IMODE(info.st_mode)
        sticky_root_directory = bool(mode & stat.S_ISVTX) and info.st_uid == 0
        if info.st_uid not in allowed_owners or (
            mode & 0o022 and not sticky_root_directory
        ):
            raise ValueError("private path parent has unsafe owner or mode")
    info = path.stat()
    if stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid not in {0, os.geteuid()}:
        raise ValueError("private path has unsafe owner or mode")
    if executable and not os.access(path, os.X_OK):
        raise ValueError("private hook must be executable")
    return path


def client_config_evidence(path_value: str) -> dict[str, str]:
    _path, raw, _private_key, _public_key, psk_value = _client_config_credentials(
        path_value
    )
    return {
        "clientConfigSha256": sha256_bytes(raw),
        "peerConfigSha256": sha256_bytes(b"ripdpi:awg-evidence-peer:v1:" + psk_value),
    }


def _client_config_credentials(
    path_value: Any,
) -> tuple[Path, bytes, bytes, bytes, bytes]:
    if not isinstance(path_value, str):
        raise ValueError("private path must be a string")
    candidate = Path(path_value)
    if (
        candidate.is_absolute()
        and not candidate.is_symlink()
        and not candidate.exists()
    ):
        raise MissingCredentials("AWG client config is missing")
    path = _secure_path(path_value, executable=False)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise MissingCredentials("AWG client config is missing") from exc
    private_key_values = re.findall(rb"(?mi)^\s*PrivateKey\s*=\s*(.*?)\s*$", raw)
    public_key_values = re.findall(rb"(?mi)^\s*PublicKey\s*=\s*(.*?)\s*$", raw)
    psk_values = re.findall(rb"(?mi)^\s*PresharedKey\s*=\s*(.*?)\s*$", raw)
    key_pattern = re.compile(rb"[A-Za-z0-9+/]{43}=")
    if (
        len(private_key_values) != 1
        or len(public_key_values) != 1
        or len(psk_values) != 1
        or key_pattern.fullmatch(private_key_values[0]) is None
        or key_pattern.fullmatch(public_key_values[0]) is None
        or key_pattern.fullmatch(psk_values[0]) is None
    ):
        raise MissingCredentials(
            "AWG client config must contain exactly one private, public, and preshared key"
        )
    return path, raw, private_key_values[0], public_key_values[0], psk_values[0]


def load_config(path: Path, client_acceptance_path: Path) -> dict[str, Any]:
    config_path = _secure_path(str(path), executable=False)
    value = json.loads(config_path.read_text())
    if not isinstance(value, dict):
        raise ValueError("runner config must be an object")
    require_fields(value, CONFIG_FIELDS, "runner config")
    if value["version"] != CONFIG_VERSION:
        raise ValueError("unsupported runner config version")
    runner_id = require_sha(value["runnerId"], SHA256_RE, "runnerId")
    client_acceptance = client_acceptance_descriptor(client_acceptance_path)
    client, _, client_private, client_public, client_psk = _client_config_credentials(
        value["clientConfigPath"]
    )
    rotated, _, rotated_private, rotated_public, rotated_psk = (
        _client_config_credentials(value["rotatedClientConfigPath"])
    )
    if client.samefile(rotated):
        raise ValueError("rotated client config must be a distinct file")
    if client_private == rotated_private:
        raise ValueError("rotated client config must use a distinct private key")
    if client_public != rotated_public:
        raise ValueError("rotated client config must retain the server peer public key")
    if client_psk == rotated_psk:
        raise ValueError("rotated client config must use a distinct preshared key")
    control_hook = _secure_path(value["serverControlHook"], executable=True)
    deploy_hook = _secure_path(value["serverDeployHook"], executable=True)
    rotation_hook = _secure_path(value["rotationHook"], executable=True)
    try:
        address = ipaddress.ip_interface(value["clientAddress"])
        echo_addresses = [
            ipaddress.ip_address(value["tcpEchoAddress"]),
            ipaddress.ip_address(value["udpEchoAddress"]),
        ]
    except (TypeError, ValueError) as exc:
        raise ValueError("client and echo addresses must be numeric IP values") from exc
    if not all(echo.is_global for echo in echo_addresses):
        raise ValueError(
            "echo addresses must be globally routable owner-controlled IPs"
        )
    for key in ("tcpEchoPort", "udpEchoPort"):
        port = require_int(value[key], key, 1)
        if port > 65535:
            raise ValueError(f"{key} exceeds 65535")
    probe_timeout = require_int(value["probeTimeoutSeconds"], "probeTimeoutSeconds", 1)
    recovery_timeout = require_int(
        value["recoveryTimeoutSeconds"], "recoveryTimeoutSeconds", 1
    )
    deploy_timeout = require_int(
        value["deployTimeoutSeconds"], "deployTimeoutSeconds", 60
    )
    if probe_timeout > 60 or recovery_timeout > 600 or deploy_timeout > 1800:
        raise ValueError("runner timeouts exceed the contract maximum")
    return {
        **value,
        "clientConfigPath": str(client),
        "rotatedClientConfigPath": str(rotated),
        "clientAddress": str(address),
        "clientAddressVersion": address.version,
        "serverControlHook": str(control_hook),
        "serverDeployHook": str(deploy_hook),
        "rotationHook": str(rotation_hook),
        "runnerIdSha256": sha256_bytes(f"ripdpi:awg-runner:v1:{runner_id}".encode()),
        "clientAcceptance": client_acceptance,
        "serverControlHookSha256": sha256_bytes(control_hook.read_bytes()),
        "serverDeployHookSha256": sha256_bytes(deploy_hook.read_bytes()),
        "rotationHookSha256": sha256_bytes(rotation_hook.read_bytes()),
        "producerSha256": sha256_bytes(Path(__file__).read_bytes()),
    }


class SystemExecutor:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.scratch = Path(tempfile.mkdtemp(prefix="ripdpi-awg-nat-"))
        os.chmod(self.scratch, 0o700)
        self.namespace: str | None = None
        self.interface: str | None = None
        self.namespace_created = False
        self.interface_created = False
        self.go_process: subprocess.Popen[bytes] | None = None
        self.capture_process: subprocess.Popen[bytes] | None = None
        self.capture_path: Path | None = None

    @staticmethod
    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        timeout = kwargs.pop("timeout", 30)
        return subprocess.run(command, check=True, timeout=timeout, **kwargs)

    @classmethod
    def _run_hook(
        cls, command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[Any]:
        try:
            return cls._run(command, **kwargs)
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 70:
                raise HookProductFailure("private hook product failure") from exc
            if exc.returncode == 75:
                raise InfrastructureUnavailable("private hook unavailable") from exc
            raise
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InfrastructureUnavailable("private hook unavailable") from exc

    def _probe(self, prefix: list[str]) -> dict[str, Any]:
        request = {
            "tcpAddress": self.config["tcpEchoAddress"],
            "tcpPort": self.config["tcpEchoPort"],
            "udpAddress": self.config["udpEchoAddress"],
            "udpPort": self.config["udpEchoPort"],
            "timeoutSeconds": self.config["probeTimeoutSeconds"],
        }
        try:
            completed = self._run(
                prefix + [sys.executable, str(Path(__file__).resolve()), "probe-child"],
                input=json.dumps(request),
                text=True,
                capture_output=True,
            )
            result = json.loads(completed.stdout)
            _validate_probe(result["tcp"], "probe.tcp")
            _validate_probe(result["udp"], "probe.udp")
            return result
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            return {
                "tcp": {"ok": False, "durationMs": None},
                "udp": {"ok": False, "durationMs": None},
            }

    def direct_probe(self) -> dict[str, Any]:
        return self._probe([])

    def deploy_source(self, source_sha: str, archive_sha256: str) -> dict[str, Any]:
        completed = self._run_hook(
            [
                self.config["serverDeployHook"],
                "deploy",
                self.config["sourceArchivePath"],
                source_sha,
                archive_sha256,
            ],
            timeout=self.config["deployTimeoutSeconds"],
            text=True,
            capture_output=True,
        )
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise ValueError("server deploy receipt must be an object")
        require_fields(value, DEPLOY_RECEIPT_FIELDS, "server deploy receipt")
        require_sha(value["deployedSourceSha"], SHA1_RE, "deployed source SHA")
        require_sha(value["deployedArchiveSha256"], SHA256_RE, "deployed archive SHA")
        return value

    def client_evidence(self, *, rotated: bool) -> dict[str, str]:
        key = "rotatedClientConfigPath" if rotated else "clientConfigPath"
        return client_config_evidence(self.config[key])

    def server_status(self) -> dict[str, Any]:
        completed = self._run_hook(
            [self.config["serverControlHook"], "status"],
            text=True,
            capture_output=True,
        )
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise ValueError("server status must be an object")
        require_fields(value, STATUS_FIELDS, "server status")
        for key in ("serviceActive", "interfaceUp"):
            if not isinstance(value[key], bool):
                raise ValueError("server status booleans are invalid")
        require_sha(value["deployedSourceSha"], SHA1_RE, "deployed source SHA")
        for key in (
            "deployedArchiveSha256",
            "serviceInvocationSha256",
            "configGenerationSha256",
            "peerConfigSha256",
        ):
            require_sha(value[key], SHA256_RE, f"server status {key}")
        for key in (
            "latestHandshakeEpoch",
            "peerRxBytes",
            "peerTxBytes",
            "natPackets",
            "natBytes",
        ):
            require_int(value[key], f"server status {key}")
        return value

    def server_action(self, action: str) -> None:
        if action not in {"restart", "reload"}:
            raise ValueError("unsupported server action")
        self._run_hook(
            [self.config["serverControlHook"], action],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stage_rotation(self) -> dict[str, Any]:
        completed = self._run_hook(
            [self.config["rotationHook"], "prepare"],
            text=True,
            capture_output=True,
        )
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise ValueError("rotation receipt must be an object")
        return value

    def finalize_rotation(self, action: str) -> dict[str, Any]:
        if action not in {"commit", "rollback"}:
            raise ValueError("unsupported rotation finalizer")
        completed = self._run_hook(
            [self.config["rotationHook"], action],
            text=True,
            capture_output=True,
        )
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise ValueError("rotation finalizer receipt must be an object")
        return value

    def _start_client(self, *, rotated: bool) -> None:
        if self.namespace is not None:
            raise RuntimeError("client namespace is already active")
        suffix = f"{os.getpid() % 100000:05d}{1 if rotated else 0}"
        self.namespace = f"awglane{suffix}"
        self.interface = f"awge{suffix}"[:15]
        config_path = self.config[
            "rotatedClientConfigPath" if rotated else "clientConfigPath"
        ]
        self._run(["ip", "netns", "add", self.namespace], capture_output=True)
        self.namespace_created = True
        stripped = self._run(
            ["awg-quick", "strip", config_path],
            text=True,
            capture_output=True,
        )
        if (
            subprocess.run(
                ["ip", "link", "show", self.interface], capture_output=True
            ).returncode
            == 0
        ):
            raise RuntimeError("client interface name is already in use")
        self.go_process = subprocess.Popen(
            ["amneziawg-go", self.interface],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            if (
                subprocess.run(
                    ["ip", "link", "show", self.interface], capture_output=True
                ).returncode
                == 0
            ):
                self.interface_created = True
                break
            if self.go_process.poll() is not None:
                raise RuntimeError("amneziawg-go exited during startup")
            time.sleep(0.1)
        else:
            raise RuntimeError("amneziawg-go interface did not appear")
        self._run(
            ["awg", "setconf", self.interface, "/dev/stdin"],
            input=stripped.stdout,
            text=True,
            capture_output=True,
        )
        self._run(["ip", "link", "set", self.interface, "netns", self.namespace])
        self._run(
            [
                "ip",
                "-n",
                self.namespace,
                "address",
                "add",
                self.config["clientAddress"],
                "dev",
                self.interface,
            ]
        )
        self._run(["ip", "-n", self.namespace, "link", "set", self.interface, "up"])
        route_family = ["-6"] if self.config["clientAddressVersion"] == 6 else []
        self._run(
            [
                "ip",
                "-n",
                self.namespace,
                *route_family,
                "route",
                "add",
                "default",
                "dev",
                self.interface,
            ]
        )
        self.capture_path = (
            self.scratch / f"capture-{len(list(self.scratch.glob('capture-*')))}.pcap"
        )
        self.capture_process = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                self.namespace,
                "tcpdump",
                "-Z",
                "root",
                "-i",
                self.interface,
                "-U",
                "-w",
                str(self.capture_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.2)
        if self.capture_process.poll() is not None:
            raise RuntimeError("tcpdump exited during startup")

    def start_client(self, *, rotated: bool) -> None:
        try:
            self._start_client(rotated=rotated)
        except BaseException as exc:
            try:
                self._cleanup_client(require_capture=False)
            except Exception as cleanup_exc:
                raise RuntimeError(
                    "partial client startup cleanup failed"
                ) from cleanup_exc
            raise exc

    def probe(self, phase: str) -> dict[str, Any]:
        if self.namespace is None:
            raise RuntimeError("client namespace is not active")
        deadline = time.monotonic() + self.config["recoveryTimeoutSeconds"]
        last = self._probe(["ip", "netns", "exec", self.namespace])
        while not _probe_ok(last) and time.monotonic() < deadline:
            time.sleep(1)
            last = self._probe(["ip", "netns", "exec", self.namespace])
        return last

    def probe_once(self, phase: str) -> dict[str, Any]:
        if self.namespace is None:
            raise RuntimeError("client namespace is not active")
        return self._probe(["ip", "netns", "exec", self.namespace])

    @staticmethod
    def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
        if process is None or process.poll() is not None:
            return
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def _cleanup_client(self, *, require_capture: bool) -> str | None:
        namespace = self.namespace
        interface = self.interface
        namespace_created = self.namespace_created
        interface_created = self.interface_created
        capture_path = self.capture_path
        cleanup_errors = False
        self._stop_process(self.capture_process)
        if namespace_created and interface_created and namespace and interface:
            subprocess.run(
                ["ip", "-n", namespace, "link", "delete", interface],
                capture_output=True,
            )
        if interface_created and interface:
            subprocess.run(["ip", "link", "delete", interface], capture_output=True)
        if namespace_created and namespace:
            subprocess.run(["ip", "netns", "delete", namespace], capture_output=True)
        self._stop_process(self.go_process)
        if namespace_created and namespace:
            namespaces = subprocess.run(
                ["ip", "netns", "list"], text=True, capture_output=True
            )
            cleanup_errors |= namespaces.returncode != 0 or any(
                line.split(maxsplit=1)[0] == namespace
                for line in namespaces.stdout.splitlines()
                if line.strip()
            )
        if interface_created and interface:
            cleanup_errors |= (
                subprocess.run(
                    ["ip", "link", "show", interface], capture_output=True
                ).returncode
                == 0
            )
        cleanup_errors |= (
            self.capture_process is not None and self.capture_process.poll() is None
        )
        cleanup_errors |= self.go_process is not None and self.go_process.poll() is None
        digest = None
        if capture_path is not None and capture_path.is_file():
            raw = capture_path.read_bytes()
            capture_path.unlink()
            if len(raw) > 24:
                digest = sha256_bytes(raw)
        if require_capture and digest is None:
            cleanup_errors = True
        cleanup_errors |= capture_path is not None and capture_path.exists()
        if cleanup_errors:
            raise RuntimeError("client cleanup or capture verification failed")
        self.capture_process = None
        self.go_process = None
        self.namespace = None
        self.interface = None
        self.namespace_created = False
        self.interface_created = False
        self.capture_path = None
        return digest

    def stop_client(self) -> str:
        digest = self._cleanup_client(require_capture=True)
        if digest is None:
            raise RuntimeError("client capture digest is missing")
        return digest

    def close(self) -> None:
        if any(
            value is not None
            for value in (
                self.namespace,
                self.interface,
                self.go_process,
                self.capture_process,
                self.capture_path,
            )
        ):
            self._cleanup_client(require_capture=False)
        shutil.rmtree(self.scratch)
        if self.scratch.exists():
            raise RuntimeError("runner scratch directory still exists")


def _roundtrip(address: str, port: int, timeout: float, *, udp: bool) -> dict[str, Any]:
    payload = secrets.token_bytes(32)
    family = (
        socket.AF_INET6
        if ipaddress.ip_address(address).version == 6
        else socket.AF_INET
    )
    started = time.monotonic()
    try:
        if udp:
            with socket.socket(family, socket.SOCK_DGRAM) as client:
                client.settimeout(timeout)
                client.sendto(payload, (address, port))
                response, _ = client.recvfrom(4096)
        else:
            with socket.socket(family, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect((address, port))
                client.sendall(payload)
                chunks = bytearray()
                while len(chunks) < len(payload):
                    chunk = client.recv(len(payload) - len(chunks))
                    if not chunk:
                        break
                    chunks.extend(chunk)
                response = bytes(chunks)
        if response != payload:
            raise OSError("echo payload mismatch")
        return {"ok": True, "durationMs": round((time.monotonic() - started) * 1000)}
    except OSError:
        return {"ok": False, "durationMs": None}


def probe_child() -> int:
    request = json.load(sys.stdin)
    result = {
        "tcp": _roundtrip(
            request["tcpAddress"],
            request["tcpPort"],
            request["timeoutSeconds"],
            udp=False,
        ),
        "udp": _roundtrip(
            request["udpAddress"],
            request["udpPort"],
            request["timeoutSeconds"],
            udp=True,
        ),
    }
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def failure_manifest(
    metadata: dict[str, Any],
    producer_sha: str,
    reason_code: str = "CONFIG_INVALID",
    engine_identity: dict[str, str] | None = None,
    client_acceptance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = int(time.time())
    empty_acceptance = {
        "format": CLIENT_ACCEPTANCE_FORMAT,
        "ripdpiSourceSha": "0" * 40,
        "apkSha256": "0" * 64,
        "reportSha256": "0" * 64,
        "startedAtEpoch": now,
        "finishedAtEpoch": now,
        "transport": "amneziawg",
        "pass": False,
        "outcomes": {field: False for field in CLIENT_ACCEPTANCE_OUTCOME_FIELDS},
    }
    empty_acceptance["correlationSha256"] = client_acceptance_correlation(
        empty_acceptance
    )
    return {
        "version": MANIFEST_VERSION,
        "sourceSha": metadata["sourceSha"],
        "engineIdentity": engine_identity
        or {"amneziawgGoCommit": "0" * 40, "amneziawgGoBinarySha256": "0" * 64},
        "clientAcceptance": client_acceptance or empty_acceptance,
        "startedAtEpoch": now,
        "finishedAtEpoch": now,
        "generatedAtEpoch": now,
        "provenance": provenance_from_metadata(metadata),
        "runnerIdSha256": "0" * 64,
        "producerDigests": {
            "runnerSha256": producer_sha,
            "serverControlHookSha256": "0" * 64,
            "serverDeployHookSha256": "0" * 64,
            "rotationHookSha256": "0" * 64,
        },
        "classification": "INFRA_UNAVAILABLE",
        "reasonCode": reason_code,
        "phases": [],
        "captureDigests": [],
        "privateLogSha256": sha256_bytes(f"{reason_code}\n".encode()),
        "serverDeployment": {
            "sourceCurrent": False,
            "archiveMatched": False,
            "receiptSha256": "0" * 64,
        },
        "rotation": {
            "prepared": False,
            "oldKeyRejected": False,
            "newKeyMatched": False,
            "committed": False,
            "rolledBack": False,
        },
        "cleanup": {
            "clientStopped": True,
            "capturesRemoved": True,
            "scratchRemoved": True,
            "serverTransactionFinalized": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--source-sha", required=True)
    run.add_argument("--executor", choices=sorted(EXECUTOR_ENTRYPOINTS))
    run.add_argument("--entrypoint-path")
    run.add_argument("--invocation-id")
    run.add_argument("--invocation-attempt", type=int)
    run.add_argument("--workflow-run-id", type=int)
    run.add_argument("--workflow-run-attempt", type=int)
    run.add_argument("--source-archive", type=Path, required=True)
    run.add_argument("--client-acceptance-descriptor", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--expected-source-sha", required=True)
    validate.add_argument("--expected-executor", choices=sorted(EXECUTOR_ENTRYPOINTS))
    validate.add_argument("--expected-invocation-id")
    validate.add_argument("--expected-invocation-attempt", type=int)
    validate.add_argument("--expected-run-id", type=int)
    validate.add_argument("--expected-run-attempt", type=int)
    validate.add_argument("--expected-source-archive-sha256", required=True)
    validate.add_argument("--expected-engine-commit")
    validate.add_argument("--expected-engine-binary-sha256")
    validate.add_argument("--expected-client-source-sha")
    validate.add_argument("--expected-client-apk-sha256")
    validate.add_argument("--expected-client-report-sha256")
    validate.add_argument("--expected-client-correlation-sha256")
    validate.add_argument("--allow-non-pass", action="store_true")
    runtime_identity = subparsers.add_parser("validate-client-runtime")
    runtime_identity.add_argument("--binary", type=Path, required=True)
    acceptance = subparsers.add_parser("validate-client-acceptance")
    acceptance.add_argument("--descriptor", type=Path, required=True)
    consume_acceptance = subparsers.add_parser("consume-client-acceptance")
    consume_acceptance.add_argument("--descriptor", type=Path, required=True)
    consume_acceptance.add_argument("--public-key", type=Path, required=True)
    consume_acceptance.add_argument("--request", type=Path, required=True)
    consume_acceptance.add_argument("--invocation-id", required=True)
    consume_acceptance.add_argument("--invocation-attempt", type=int, required=True)
    consume_acceptance.add_argument("--output", type=Path, required=True)
    request_acceptance = subparsers.add_parser("create-client-acceptance-request")
    request_acceptance.add_argument("--output", type=Path, required=True)
    request_acceptance.add_argument("--invocation-id", required=True)
    request_acceptance.add_argument("--invocation-attempt", type=int, required=True)
    request_acceptance.add_argument("--valid-seconds", type=int, default=300)
    recurring = subparsers.add_parser("validate-recurring")
    recurring.add_argument("--initial", type=Path, required=True)
    recurring.add_argument("--recurring", type=Path, required=True)
    retained = subparsers.add_parser("validate-retained-pass")
    retained.add_argument("--manifest", type=Path, required=True)
    record = subparsers.add_parser("record-recurring")
    record.add_argument("--manifest", type=Path, required=True)
    record.add_argument("--state-dir", type=Path, required=True)
    record.add_argument("--lock-path", type=Path, required=True)
    record.add_argument("--lock-fd", type=int)
    record.add_argument("--expected-source-sha", required=True)
    record.add_argument("--expected-source-archive-sha256", required=True)
    record.add_argument("--expected-executor", choices=sorted(EXECUTOR_ENTRYPOINTS))
    record.add_argument("--expected-invocation-id")
    record.add_argument("--expected-invocation-attempt", type=int)
    record.add_argument("--expected-engine-commit")
    record.add_argument("--expected-engine-binary-sha256")
    record.add_argument("--expected-client-source-sha")
    record.add_argument("--expected-client-apk-sha256")
    record.add_argument("--expected-client-report-sha256")
    record.add_argument("--expected-client-correlation-sha256")
    subparsers.add_parser("probe-child")
    args = parser.parse_args(argv)
    if args.command == "probe-child":
        return probe_child()
    if args.command == "validate-client-runtime":
        try:
            identity = validate_runtime_engine_identity(args.binary)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"real-VPS AWG/NAT engine identity invalid: {exc}", file=sys.stderr)
            return 1
        sys.stdout.buffer.write(canonical_json_bytes(identity))
        return 0
    if args.command == "validate-client-acceptance":
        try:
            value = client_acceptance_descriptor(args.descriptor)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"real-VPS AWG/NAT client acceptance invalid: {exc}", file=sys.stderr)
            return 1
        sys.stdout.buffer.write(canonical_json_bytes(value))
        return 0
    if args.command == "consume-client-acceptance":
        try:
            consume_client_acceptance_handoff(
                args.descriptor,
                args.public_key,
                request=args.request,
                expected_invocation_id=args.invocation_id,
                expected_invocation_attempt=args.invocation_attempt,
                output=args.output,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"real-VPS AWG/NAT client handoff invalid: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "create-client-acceptance-request":
        try:
            nonce = create_client_acceptance_request(
                args.output,
                args.invocation_id,
                invocation_attempt=args.invocation_attempt,
                valid_seconds=args.valid_seconds,
            )
        except (OSError, ValueError) as exc:
            print(f"real-VPS AWG/NAT client request invalid: {exc}", file=sys.stderr)
            return 1
        print(nonce)
        return 0
    if args.command == "validate-recurring":
        try:
            initial_raw = args.initial.read_bytes()
            recurring_raw = args.recurring.read_bytes()
            initial = json.loads(initial_raw)
            recurring_value = json.loads(recurring_raw)
            if initial_raw != canonical_json_bytes(
                initial
            ) or recurring_raw != canonical_json_bytes(recurring_value):
                raise ValueError("recurring evidence is not canonical JSON")
            validate_recurring_pair(initial, recurring_value)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(
                f"real-VPS AWG/NAT recurring evidence invalid: {exc}", file=sys.stderr
            )
            return 1
        return 0
    if args.command == "validate-retained-pass":
        try:
            value = _private_json_descriptor(
                args.manifest, "retained evidence", max_bytes=262144
            )
            validate_manifest(value, expected_source_sha=value.get("sourceSha", ""))
            if value["classification"] != "PASS":
                raise ValueError("retained evidence is not PASS")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"real-VPS AWG/NAT retained evidence invalid: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "record-recurring":
        try:
            state = record_recurring_manifest_path(
                args.manifest,
                args.state_dir,
                lock_path=args.lock_path,
                lock_fd=args.lock_fd,
                expected={
                    "expected_source_sha": args.expected_source_sha,
                    "expected_source_archive_sha256": args.expected_source_archive_sha256,
                    "expected_executor": args.expected_executor,
                    "expected_invocation_id": args.expected_invocation_id,
                    "expected_invocation_attempt": args.expected_invocation_attempt,
                    "expected_engine_commit": args.expected_engine_commit,
                    "expected_engine_binary_sha256": args.expected_engine_binary_sha256,
                    "expected_client_source_sha": args.expected_client_source_sha,
                    "expected_client_apk_sha256": args.expected_client_apk_sha256,
                    "expected_client_report_sha256": args.expected_client_report_sha256,
                    "expected_client_correlation_sha256": args.expected_client_correlation_sha256,
                },
            )
        except (OSError, ValueError, json.JSONDecodeError, RecurringStateBusy) as exc:
            print(f"real-VPS AWG/NAT recurring state invalid: {exc}", file=sys.stderr)
            return 1
        if state == "pending":
            print("initial recurring observation is pending", file=sys.stderr)
            return 1
        return 0
    if args.command == "validate":
        try:
            expected_invocation_id = args.expected_invocation_id
            if expected_invocation_id is None and args.expected_run_id is not None:
                expected_invocation_id = str(args.expected_run_id)
            expected_invocation_attempt = args.expected_invocation_attempt
            if (
                expected_invocation_attempt is None
                and args.expected_run_attempt is not None
            ):
                expected_invocation_attempt = args.expected_run_attempt
            raw = args.manifest.read_bytes()
            manifest = json.loads(raw)
            if raw != canonical_json_bytes(manifest):
                raise ValueError("manifest is not canonical JSON")
            validate_manifest(
                manifest,
                expected_source_sha=args.expected_source_sha,
                expected_executor=args.expected_executor,
                expected_invocation_id=expected_invocation_id,
                expected_invocation_attempt=expected_invocation_attempt,
                expected_source_archive_sha256=args.expected_source_archive_sha256,
                expected_engine_commit=args.expected_engine_commit,
                expected_engine_binary_sha256=args.expected_engine_binary_sha256,
                expected_client_source_sha=args.expected_client_source_sha,
                expected_client_apk_sha256=args.expected_client_apk_sha256,
                expected_client_report_sha256=args.expected_client_report_sha256,
                expected_client_correlation_sha256=args.expected_client_correlation_sha256,
            )
            return (
                0 if args.allow_non_pass or manifest["classification"] == "PASS" else 1
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"real-VPS AWG/NAT evidence invalid: {exc}", file=sys.stderr)
            return 1

    try:
        source_archive = args.source_archive.resolve(strict=True)
        if args.source_archive.is_symlink() or not source_archive.is_file():
            raise OSError("source archive must be a regular file")
        source_archive_sha256 = sha256_bytes(source_archive.read_bytes())
    except OSError:
        source_archive = args.source_archive
        source_archive_sha256 = "0" * 64
    executor = args.executor or "github_actions"
    entrypoint_path = args.entrypoint_path or EXECUTOR_ENTRYPOINTS[executor]
    if entrypoint_path != EXECUTOR_ENTRYPOINTS[executor]:
        raise ValueError("entrypoint path does not match executor")
    invocation_id = args.invocation_id
    if invocation_id is None and args.workflow_run_id is not None:
        invocation_id = str(args.workflow_run_id)
    invocation_attempt = args.invocation_attempt
    if invocation_attempt is None:
        invocation_attempt = args.workflow_run_attempt
    if invocation_id is None or invocation_attempt is None:
        raise ValueError("invocation id and attempt are required")
    metadata = {
        "sourceSha": require_sha(args.source_sha, SHA1_RE, "source SHA"),
        "sourceArchiveSha256": source_archive_sha256,
        "executor": executor,
        "entrypointPath": entrypoint_path,
        "invocationId": require_invocation_id(invocation_id),
        "invocationAttempt": require_int(invocation_attempt, "invocation attempt", 1),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    producer_sha = sha256_bytes(Path(__file__).read_bytes())
    try:
        config = load_config(args.config, args.client_acceptance_descriptor)
    except MissingCredentials:
        manifest = failure_manifest(
            metadata, producer_sha, reason_code="MISSING_CREDENTIALS"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        manifest = failure_manifest(metadata, producer_sha)
    else:
        missing = [
            command
            for command in ("ip", "awg", "awg-quick", "amneziawg-go", "tcpdump")
            if shutil.which(command) is None
        ]
        if os.geteuid() != 0 or missing or source_archive_sha256 == "0" * 64:
            manifest = failure_manifest(
                metadata,
                producer_sha,
                reason_code="PREREQUISITE_MISSING",
                client_acceptance=config["clientAcceptance"],
            )
        else:
            try:
                engine_binary = Path(shutil.which("amneziawg-go") or "")
                config["engineIdentity"] = validate_runtime_engine_identity(
                    engine_binary
                )
                config["sourceArchivePath"] = str(source_archive)
                executor = SystemExecutor(config)

                def interrupt_lane(signum: int, _frame: Any) -> None:
                    raise LaneFailure("INFRA_UNAVAILABLE", "INTERRUPTED")

                signal.signal(signal.SIGTERM, interrupt_lane)
                signal.signal(signal.SIGINT, interrupt_lane)
                manifest = run_lane(config, executor, metadata)
            except (OSError, ValueError):
                manifest = failure_manifest(
                    metadata,
                    producer_sha,
                    reason_code="RUNNER_EXCEPTION",
                    engine_identity=config.get("engineIdentity"),
                    client_acceptance=config["clientAcceptance"],
                )
    write_canonical_json(args.output, manifest)
    validate_manifest(manifest, expected_source_sha=args.source_sha)
    return 0 if manifest["classification"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
