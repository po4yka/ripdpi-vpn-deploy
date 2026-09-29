#!/usr/bin/env python3
"""Advance the fixed disposable observability staging acceptance sequence.

The controller accepts only repository-defined actions.  It publishes one
redacted receipt per invocation so long waits and human Telegram observations
can be resumed without turning the interface into an arbitrary remote runner.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable
import urllib.error
import urllib.request

import fleet_inspection
import yaml

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "MON-1790650904289505"
CHANGE = "staging-observability-telegram-acceptance"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40,64}$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
OBSERVATION_KEYS = (
    "primary_lifecycle",
    "secondary_lifecycle",
    "deadman_loss_primary",
    "primary_authority_loss_secondary",
)
STEP_OBSERVATIONS = {
    "primary-lifecycle": ("primary_lifecycle",),
    "deadman-lifecycle": ("secondary_lifecycle",),
    "control-service-loss": ("secondary_lifecycle",),
    "control-host-loss": ("secondary_lifecycle",),
    "deadman-service-loss": ("deadman_loss_primary",),
    "primary-authority-loss": ("primary_authority_loss_secondary",),
}
OBSERVATION_STEPS = tuple(STEP_OBSERVATIONS)
ACCEPTANCE_CHECKS = (
    "fresh-metrics",
    "ingestion-negative",
    "agent-wal",
    "staleness",
    "grouping-inhibition",
    "finite-silence",
    "primary-lifecycle",
    "deadman-lifecycle",
    "control-service-loss",
    "control-host-loss",
    "deadman-service-loss",
    "primary-authority-loss",
    "canary-sender-rotation",
    "primary-bot-rotation",
    "secondary-bot-rotation",
    "old-material-rejection",
    "invalid-candidate-refusal",
    "valid-candidate-activation",
    "control-plane-rollback",
)
STEPS = ACCEPTANCE_CHECKS + ("component-removal",)
STEP_TARGETS = {
    "fresh-metrics": "control-plane",
    "ingestion-negative": "canary-to-control-plane",
    "agent-wal": "canary-to-control-plane",
    "staleness": "canary-to-control-plane",
    "grouping-inhibition": "primary-route",
    "finite-silence": "primary-route",
    "primary-lifecycle": "primary-route",
    "deadman-lifecycle": "secondary-route",
    "control-service-loss": "control-plane",
    "control-host-loss": "control-plane-host",
    "deadman-service-loss": "deadman",
    "primary-authority-loss": "primary-route",
    "canary-sender-rotation": "canary",
    "primary-bot-rotation": "primary-route",
    "secondary-bot-rotation": "secondary-route",
    "old-material-rejection": "primary-and-secondary-route",
    "invalid-candidate-refusal": "control-plane",
    "valid-candidate-activation": "control-plane",
    "control-plane-rollback": "control-plane",
    "component-removal": "staging-components",
}
STEP_RESTORES = {
    "fresh-metrics": "none",
    "ingestion-negative": "none",
    "agent-wal": "start-control-plane-ingress",
    "staleness": "restore-canary-producer-and-sender",
    "grouping-inhibition": "resolve-staging-matrix-alerts",
    "finite-silence": "expire-delete-staging-silence",
    "primary-lifecycle": "resolve-critical-drill",
    "deadman-lifecycle": "restore-control-plane-pulses",
    "control-service-loss": "start-control-plane-services",
    "control-host-loss": "power-on-control-plane-host",
    "deadman-service-loss": "start-deadman-service",
    "primary-authority-loss": "activate-primary-replacement",
    "canary-sender-rotation": "restore-canary-generation",
    "primary-bot-rotation": "restore-control-plane-generation",
    "secondary-bot-rotation": "restore-deadman-generation",
    "old-material-rejection": "none",
    "invalid-candidate-refusal": "preserve-current-control-plane-generation",
    "valid-candidate-activation": "restore-prior-control-plane-generation",
    "control-plane-rollback": "restore-prior-control-plane-generation",
    "component-removal": "retain-provider-resources",
}
STEP_MIN_DEADLINES = {
    "fresh-metrics": 130,
    "ingestion-negative": 120,
    "agent-wal": 600,
    "staleness": 1800,
    "grouping-inhibition": 300,
    "finite-silence": 300,
    "primary-lifecycle": 4800,
    "deadman-lifecycle": 4800,
    "control-service-loss": 1200,
    "control-host-loss": 1800,
    "deadman-service-loss": 1200,
    "primary-authority-loss": 1500,
    "canary-sender-rotation": 600,
    "primary-bot-rotation": 600,
    "secondary-bot-rotation": 600,
    "old-material-rejection": 60,
    "invalid-candidate-refusal": 600,
    "valid-candidate-activation": 600,
    "control-plane-rollback": 600,
    "component-removal": 900,
}
STEP_MAX_DEADLINES = {
    name: max(7200, minimum) for name, minimum in STEP_MIN_DEADLINES.items()
}
INPUT_KEYS = {
    "control_plane_vars",
    "control_plane_secrets",
    "candidate_control_plane_vars",
    "candidate_control_plane_secrets",
    "deadman_vars",
    "deadman_secrets",
    "canary_vars",
    "canary_secrets",
    "canary_old_generation",
    "rollback_manifest",
    "invalid_control_plane_vars",
    "silence_owner",
    "hetzner_binding",
    "primary_old_token",
    "secondary_old_token",
    "observations",
}


class AcceptanceError(Exception):
    """A bounded, non-sensitive operator failure."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _safe_parent(path: Path) -> None:
    absolute = path.absolute()
    current = absolute.parent
    uid = os.getuid()
    while current != current.parent:
        metadata = current.stat(follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            raise AcceptanceError("private path rejected")
        if current == absolute.parent and (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != uid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise AcceptanceError("private path rejected")
        current = current.parent


def _private_file(path: Path, category: str) -> tuple[bytes, os.stat_result]:
    try:
        absolute = path.absolute()
        _safe_parent(absolute)
        descriptor = os.open(
            absolute,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or metadata.st_size > fleet_inspection.LIMIT
            ):
                raise AcceptanceError(category)
            raw = b""
            while len(raw) <= fleet_inspection.LIMIT:
                chunk = os.read(
                    descriptor, min(65536, fleet_inspection.LIMIT + 1 - len(raw))
                )
                if not chunk:
                    break
                raw += chunk
            if len(raw) > fleet_inspection.LIMIT:
                raise AcceptanceError(category)
            return raw, metadata
        finally:
            os.close(descriptor)
    except AcceptanceError:
        raise
    except OSError:
        raise AcceptanceError(category) from None


def _private_json(path: Path, category: str) -> tuple[dict[str, Any], bytes]:
    raw, _ = _private_file(path, category)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise AcceptanceError(category) from None
    if not isinstance(value, dict) or raw != _canonical(value):
        raise AcceptanceError(category)
    return value, raw


def _atomic_private(path: Path, value: dict[str, Any]) -> None:
    absolute = path.absolute()
    _safe_parent(absolute)
    if os.path.lexists(absolute):
        try:
            metadata = absolute.stat(follow_symlinks=False)
        except OSError:
            raise AcceptanceError("private output rejected") from None
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise AcceptanceError("private output rejected")
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{absolute.name}.", dir=absolute.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, _canonical(value))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, absolute)
        directory = os.open(absolute.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def _path_mapping(value: object, keys: set[str], category: str) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or any(
            not isinstance(item, str) or not item.startswith("/")
            for item in value.values()
        )
    ):
        raise AcceptanceError(category)
    return dict(value)


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    value, raw = _private_json(path, "private manifest required")
    try:
        if (
            set(value)
            != {
                "schema_version",
                "task_id",
                "change",
                "environment",
                "source_revision",
                "deployable_digest",
                "inventory",
                "known_hosts",
                "hosts",
                "inputs",
                "approvals",
            }
            or value["schema_version"] != 1
            or value["task_id"] != TASK_ID
            or value["change"] != CHANGE
            or value["environment"] != "staging"
            or not REVISION.fullmatch(value["source_revision"])
            or not HEX64.fullmatch(value["deployable_digest"])
            or not isinstance(value["inventory"], str)
            or not value["inventory"].startswith("/")
            or not isinstance(value["known_hosts"], str)
            or not value["known_hosts"].startswith("/")
            or set(value["hosts"]) != {"canary", "control-plane", "deadman"}
            or any(
                not isinstance(alias, str) or not SLUG.fullmatch(alias)
                for alias in value["hosts"].values()
            )
            or len(set(value["hosts"].values())) != 3
        ):
            raise AcceptanceError("manifest rejected")
        value["inputs"] = _path_mapping(
            value["inputs"], INPUT_KEYS, "manifest rejected"
        )
        value["approvals"] = _path_mapping(
            value["approvals"], set(STEPS), "manifest rejected"
        )
    except (KeyError, TypeError):
        raise AcceptanceError("manifest rejected") from None
    return value, hashlib.sha256(raw).hexdigest()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _timestamp(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_time(value: object) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != dt.timezone.utc:
        raise ValueError
    return parsed


def _approval(manifest: dict[str, Any], step: str, now: dt.datetime) -> dict[str, Any]:
    value, _ = _private_json(Path(manifest["approvals"][step]), "approval rejected")
    try:
        if (
            set(value)
            != {
                "schema_version",
                "task_id",
                "change",
                "action",
                "target",
                "restore_action",
                "approved",
                "approved_at",
                "expires_at",
                "deadline_seconds",
                "cancellation_condition",
            }
            or value["schema_version"] != 1
            or value["task_id"] != TASK_ID
            or value["change"] != CHANGE
            or value["action"] != step
            or value["target"] != STEP_TARGETS[step]
            or value["restore_action"] != STEP_RESTORES[step]
            or value["approved"] is not True
            or value["cancellation_condition"] != "restore-and-stop"
            or not isinstance(value["deadline_seconds"], int)
            or not STEP_MIN_DEADLINES[step]
            <= value["deadline_seconds"]
            <= STEP_MAX_DEADLINES[step]
        ):
            raise ValueError
        approved_at = _parse_time(value["approved_at"])
        expires_at = _parse_time(value["expires_at"])
        if not approved_at <= now < expires_at:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise AcceptanceError("approval rejected") from None
    return value


def _observations(
    manifest: dict[str, Any],
    *,
    step: str | None = None,
    started_at: str | None = None,
    receipt_sha256: str | None = None,
    completed_at: str | None = None,
) -> dict[str, bool]:
    value, _ = _private_json(
        Path(manifest["inputs"]["observations"]), "observations rejected"
    )
    rows = value.get("rows") if isinstance(value, dict) else None
    if (
        set(value) != {"schema_version", "rows"}
        or value.get("schema_version") != 1
        or not isinstance(rows, dict)
        or set(rows) != set(OBSERVATION_STEPS)
    ):
        raise AcceptanceError("observations rejected")
    current = _utc_now()
    observed_rows: dict[str, bool] = {}
    for name in OBSERVATION_STEPS:
        record = rows[name]
        if (
            not isinstance(record, dict)
            or set(record)
            != {"observed", "started_at", "observed_at", "receipt_sha256"}
            or type(record.get("observed")) is not bool
        ):
            raise AcceptanceError("observations rejected")
        if record["observed"]:
            try:
                row_started = _parse_time(record["started_at"])
                observed_at = _parse_time(record["observed_at"])
                if observed_at < row_started or observed_at > current:
                    raise ValueError
                if not HEX64.fullmatch(str(record["receipt_sha256"])):
                    raise ValueError
            except (TypeError, ValueError):
                raise AcceptanceError("observations rejected") from None
        elif (
            record["started_at"] is not None
            or record["observed_at"] is not None
            or record["receipt_sha256"] is not None
        ):
            raise AcceptanceError("observations rejected")
        observed_rows[name] = record["observed"]
    if step in STEP_OBSERVATIONS:
        record = rows[step]
        if (
            record["observed"] is not True
            or not isinstance(started_at, str)
            or record["started_at"] != started_at
            or record["receipt_sha256"] != receipt_sha256
        ):
            raise AcceptanceError("human observation required")
        try:
            if _parse_time(record["observed_at"]) < _parse_time(completed_at):
                raise ValueError
        except (TypeError, ValueError):
            raise AcceptanceError("human observation required") from None
    return {
        "primary_lifecycle": observed_rows["primary-lifecycle"],
        "secondary_lifecycle": all(
            observed_rows[name]
            for name in (
                "deadman-lifecycle",
                "control-service-loss",
                "control-host-loss",
            )
        ),
        "deadman_loss_primary": observed_rows["deadman-service-loss"],
        "primary_authority_loss_secondary": observed_rows["primary-authority-loss"],
    }


def new_journal(manifest: dict[str, Any], manifest_digest: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "change": CHANGE,
        "manifest_sha256": manifest_digest,
        "source_revision": manifest["source_revision"],
        "deployable_digest": manifest["deployable_digest"],
        "status": "active",
        "completed_checks": [],
        "current_step": None,
        "human_observations": {key: False for key in OBSERVATION_KEYS},
        "components_removed": False,
    }


def _journal(path: Path, manifest: dict[str, Any], digest: str) -> dict[str, Any]:
    if not path.exists():
        return new_journal(manifest, digest)
    value, _ = _private_json(path, "journal rejected")
    cleanup_keys = {
        "schema_version",
        "task_id",
        "change",
        "source_revision",
        "deployable_digest",
        "status",
        "completed_checks",
        "human_observations",
        "components_removed",
    }
    if set(value) == cleanup_keys:
        if (
            value.get("schema_version") != 1
            or value.get("task_id") != TASK_ID
            or value.get("change") != CHANGE
            or value.get("source_revision") != manifest["source_revision"]
            or value.get("deployable_digest") != manifest["deployable_digest"]
            or value.get("status") != "ready-for-cleanup"
            or value.get("completed_checks") != sorted(ACCEPTANCE_CHECKS)
            or value.get("human_observations")
            != {key: True for key in OBSERVATION_KEYS}
            or value.get("components_removed") is not True
        ):
            raise AcceptanceError("journal rejected")
        return value
    expected_keys = {
        "schema_version",
        "task_id",
        "change",
        "manifest_sha256",
        "source_revision",
        "deployable_digest",
        "status",
        "completed_checks",
        "current_step",
        "human_observations",
        "components_removed",
    }
    if (
        set(value) != expected_keys
        or value["schema_version"] != 1
        or value["task_id"] != TASK_ID
        or value["change"] != CHANGE
        or value["manifest_sha256"] != digest
        or value["source_revision"] != manifest["source_revision"]
        or value["deployable_digest"] != manifest["deployable_digest"]
        or value["status"] not in {"active", "incomplete", "ready-for-cleanup"}
        or not isinstance(value["completed_checks"], list)
        or value["completed_checks"]
        != [name for name in ACCEPTANCE_CHECKS if name in value["completed_checks"]]
        or set(value["human_observations"]) != set(OBSERVATION_KEYS)
        or any(
            type(value["human_observations"][key]) is not bool
            for key in OBSERVATION_KEYS
        )
        or type(value["components_removed"]) is not bool
    ):
        raise AcceptanceError("journal rejected")
    current = value["current_step"]
    if current is not None and (
        not isinstance(current, dict)
        or set(current) != {"name", "started_at"}
        or current.get("name") not in STEPS
        or not isinstance(current.get("started_at"), str)
    ):
        raise AcceptanceError("journal rejected")
    return value


def _debug_disabled() -> None:
    for name in ("ANSIBLE_DEBUG", "ANSIBLE_DIFF_ALWAYS", "TF_LOG", "TF_LOG_PATH"):
        if os.environ.get(name, "").strip().lower() in TRUE_VALUES or (
            name.startswith("TF_") and os.environ.get(name, "").strip()
        ):
            raise AcceptanceError("debug output forbidden")


def _source_identity(manifest: dict[str, Any]) -> None:
    try:
        result = subprocess.run(
            [str(ROOT / "scripts" / "deploy-source-identity.sh"), "--identity"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            timeout=15,
        )
        revision, digest = result.stdout.strip().split()
    except (OSError, subprocess.SubprocessError, ValueError):
        raise AcceptanceError("source identity unavailable") from None
    if (
        revision != manifest["source_revision"]
        or digest != manifest["deployable_digest"]
    ):
        raise AcceptanceError("source identity drift")
    try:
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                "Makefile",
                "ansible",
                "scripts",
                "terraform",
                "requirements.yml",
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
        protected = subprocess.run(
            ["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        raise AcceptanceError("source cleanliness unavailable") from None
    if status.returncode != 0:
        raise AcceptanceError("source cleanliness unavailable")
    if status.stdout or protected.stdout.strip() != revision:
        raise AcceptanceError("clean protected-main source required")


def _operator(
    manifest: dict[str, Any],
    command: str,
    component: str,
    *,
    confirm: bool = False,
    variables: str | None = None,
    secrets: str | None = None,
    expect_role_guard_refusal: bool = False,
) -> dict[str, Any]:
    host_key = {
        "agent": "canary",
        "control-plane": "control-plane",
        "deadman": "deadman",
    }[component]
    prefix = {
        "agent": "canary",
        "control-plane": "control_plane",
        "deadman": "deadman",
    }[component]
    argv = [
        sys.executable,
        str(ROOT / "scripts" / "observability-operator.py"),
        command,
        "--inventory",
        manifest["inventory"],
        "--host",
        manifest["hosts"][host_key],
        "--environment",
        "staging",
        "--component",
        component,
        "--known-hosts",
        manifest["known_hosts"],
    ]
    if command in {"render", "validate", "deploy", "rotate", "rollback"}:
        argv.extend(
            [
                "--secrets",
                secrets or manifest["inputs"][f"{prefix}_secrets"],
                "--vars",
                variables or manifest["inputs"][f"{prefix}_vars"],
            ]
        )
    elif command == "remove":
        argv.extend(["--vars", manifest["inputs"][f"{prefix}_vars"]])
    if command == "rollback":
        argv.extend(["--rollback-manifest", manifest["inputs"]["rollback_manifest"]])
    if expect_role_guard_refusal:
        if command != "rotate" or component != "control-plane":
            raise AcceptanceError("role guard expectation rejected")
        argv.append("--expect-role-guard-refusal")
    if confirm:
        argv.append("--confirm")
    result = subprocess.run(
        argv,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=900,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"ANSIBLE_DEBUG", "ANSIBLE_DIFF_ALWAYS"}
        },
    )
    if result.returncode:
        raise AcceptanceError("bounded lifecycle action failed")
    try:
        if len(result.stdout) > 16_384:
            raise ValueError
        value = json.loads(result.stdout)
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 1
            or value.get("component") != component
            or value.get("host") != manifest["hosts"][host_key]
            or value.get("controller_source_revision") != manifest["source_revision"]
            or value.get("controller_deployable_digest")
            != manifest["deployable_digest"]
        ):
            raise ValueError
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise AcceptanceError("bounded lifecycle result rejected") from None
    return value


def _selected_host(manifest: dict[str, Any], role: str) -> dict[str, Any]:
    section = {
        "canary": "vpn",
        "control-plane": "vpn-observability-control",
        "deadman": "vpn-observability-deadman",
    }[role]
    try:
        return fleet_inspection.select_hosts(
            Path(manifest["inventory"]),
            [manifest["hosts"][role]],
            primary_section=section,
            include_variables=True,
        )[0]
    except (OSError, fleet_inspection.InspectionError):
        raise AcceptanceError("exact inventory host rejected") from None


def _remote(manifest: dict[str, Any], role: str, program: bytes, timeout: int) -> bytes:
    host = _selected_host(manifest, role)
    variables = host.get("variables", {})
    expected = "vpn" if role == "canary" else role
    if (
        variables.get("env") != "staging"
        or variables.get("observability_host_class") != expected
    ):
        raise AcceptanceError("inventory scope rejected")
    try:
        command = fleet_inspection.ssh_command(host, Path(manifest["known_hosts"]))
        return fleet_inspection.bounded_command(
            command,
            timeout=timeout,
            limit=8192,
            input_bytes=program,
            environment={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
    except (OSError, fleet_inspection.InspectionError):
        raise AcceptanceError("bounded remote action failed") from None


def _metrics_program() -> bytes:
    return b"""import json, time, urllib.parse, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
query = urllib.parse.urlencode({"query":"max(vpn_observability_adapter_collected_timestamp_seconds)"})
def sample():
    with opener.open("http://127.0.0.1:9090/api/v1/query?" + query, timeout=5) as response:
        raw = response.read(65537)
    value = json.loads(raw)
    result = value.get("data", {}).get("result", [])
    if len(raw) > 65536 or value.get("status") != "success" or len(result) != 1:
        raise SystemExit(2)
    return float(result[0]["value"][1])
first = sample(); time.sleep(65); second = sample()
if second <= first:
    raise SystemExit(2)
print(json.dumps({"schema_version":1,"state":"advancing","metric":"vpn_observability_adapter_collected_timestamp_seconds"}, sort_keys=True))
"""


def _ingestion_negative_program() -> bytes:
    return b"""import json, os, re, socket, ssl, stat
from urllib.parse import urlsplit
root="/etc/observability-agent/credentials"
current=os.path.join(root,"current")
resolved=os.path.realpath(current)
generations=os.path.join(root,"generations")+os.sep
if not os.path.islink(current) or not resolved.startswith(generations): raise SystemExit(2)
for name,mode in (("prometheus.yml",0o644),("receiver-ca.crt",0o600),("client.crt",0o600),("client.key",0o600)):
 path=os.path.join(resolved,name); info=os.stat(path,follow_symlinks=False)
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=mode or info.st_nlink!=1: raise SystemExit(2)
config=open(os.path.join(resolved,"prometheus.yml"),encoding="utf-8").read(65537)
urls=re.findall(r'^\\s*- url: "(https://[^"\\s]+)"$',config,re.M)
snis=re.findall(r'^\\s*server_name: "([^"\\s]+)"$',config,re.M)
if len(urls)!=1 or len(snis)!=1: raise SystemExit(2)
parsed=urlsplit(urls[0])
if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment: raise SystemExit(2)
port=parsed.port or 443
def status(path,method="POST",identity=True,tls=True,body=b"x"):
 sock=socket.create_connection((parsed.hostname,port),timeout=5)
 try:
  if tls:
   context=ssl.create_default_context(cafile=os.path.join(resolved,"receiver-ca.crt"))
   if identity: context.load_cert_chain(os.path.join(resolved,"client.crt"),os.path.join(resolved,"client.key"))
   sock=context.wrap_socket(sock,server_hostname=snis[0])
  request=(method+" "+path+" HTTP/1.1\\r\\nHost: "+snis[0]+"\\r\\nConnection: close\\r\\nContent-Type: application/x-protobuf\\r\\nContent-Length: "+str(len(body))+"\\r\\n\\r\\n").encode()+body
  sock.sendall(request); raw=sock.recv(4097)
  match=re.match(br"HTTP/1[.]1 ([0-9]{3}) ",raw)
  return int(match.group(1)) if match else None
 finally: sock.close()
valid=status(parsed.path)
if valid not in (400,415): raise SystemExit(2)
def http_rejected(*args,**kwargs):
 code=status(*args,**kwargs)
 return code is not None and not 200<=code<300
def transport_or_http_rejected(*args,**kwargs):
 try:
  code=status(*args,**kwargs)
 except (ssl.SSLError,ConnectionError,OSError):
  return True
 return code is not None and not 200<=code<300
wrong_node=parsed.path.rsplit("/",1)[0]+"/rejected-cross-node"
checks=(http_rejected(wrong_node),http_rejected(parsed.path,method="GET",body=b""),http_rejected("/api/v1/query",method="GET",body=b""),http_rejected("/-/ready",method="GET",body=b""),transport_or_http_rejected(parsed.path,tls=False),transport_or_http_rejected(parsed.path,identity=False))
if not all(checks): raise SystemExit(2)
print(json.dumps({"schema_version":1,"state":"verified"},sort_keys=True))
"""


def _wal_metrics_program() -> bytes:
    return b"""import json, re, urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open("http://127.0.0.1:19090/metrics",timeout=5) as response: raw=response.read(1048577)
if len(raw)>1048576: raise SystemExit(2)
text=raw.decode("utf-8")
names=("prometheus_remote_storage_samples_pending","prometheus_remote_storage_samples_failed_total","prometheus_remote_storage_samples_retried_total","prometheus_remote_storage_samples_dropped_total","prometheus_remote_storage_queue_highest_timestamp_seconds","prometheus_remote_storage_queue_highest_sent_timestamp_seconds")
values={}
for name in names:
 matches=[float(item) for item in re.findall(r"^"+re.escape(name)+r"(?:\\{[^}]*\\})? ([0-9.eE+-]+)$",text,re.M)]
 if not matches: raise SystemExit(2)
 values[name]=sum(matches) if name.endswith(("pending","total")) else max(matches)
values["schema_version"]=1; values["state"]="sampled"
print(json.dumps(values,sort_keys=True))
"""


def _wal_sample(raw: bytes) -> dict[str, float]:
    names = {
        "prometheus_remote_storage_samples_pending",
        "prometheus_remote_storage_samples_failed_total",
        "prometheus_remote_storage_samples_retried_total",
        "prometheus_remote_storage_samples_dropped_total",
        "prometheus_remote_storage_queue_highest_timestamp_seconds",
        "prometheus_remote_storage_queue_highest_sent_timestamp_seconds",
    }
    try:
        value = json.loads(raw)
        if (
            set(value) != names | {"schema_version", "state"}
            or value["schema_version"] != 1
            or value["state"] != "sampled"
            or any(type(value[name]) not in {int, float} for name in names)
            or any(value[name] < 0 for name in names)
        ):
            raise ValueError
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise AcceptanceError("agent WAL evidence rejected") from None
    return {name: float(value[name]) for name in names}


def _stale_producer_program(action: str) -> bytes:
    if action not in {"inject", "restore"}:
        raise AcceptanceError("stale producer action rejected")
    return f"""import json, os, stat, subprocess, tempfile, time
action={action!r}
path="/var/lib/vpn-watchdog/state"
directory="/var/lib/observability-staging-acceptance"
journal=directory+"/staleness.json"
try: os.mkdir(directory,0o700)
except FileExistsError: pass
directory_info=os.stat(directory,follow_symlinks=False)
if not stat.S_ISDIR(directory_info.st_mode) or directory_info.st_uid!=0 or stat.S_IMODE(directory_info.st_mode)!=0o700: raise SystemExit(2)
def sync_directory():
 descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try: os.fsync(descriptor)
 finally: os.close(descriptor)
def write(value):
 payload=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\\n").encode(); temporary=None
 try:
  descriptor,temporary=tempfile.mkstemp(prefix=".staleness-",dir=directory)
  with os.fdopen(descriptor,"wb") as stream:
   os.fchmod(stream.fileno(),0o600); stream.write(payload); stream.flush(); os.fsync(stream.fileno())
  os.replace(temporary,journal); temporary=None; sync_directory()
 finally:
  if temporary and os.path.lexists(temporary): os.unlink(temporary)
def read():
 descriptor=os.open(journal,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(descriptor,"rb") as stream:
  info=os.fstat(stream.fileno()); raw=stream.read(4097)
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or len(raw)>4096: raise SystemExit(2)
 value=json.loads(raw)
 base={{"schema_version","path","phase","timer_active"}}
 if value.get("phase")=="pending": expected=base
 elif value.get("phase")=="holding": expected=base|{{"device","inode","atime_ns","mtime_ns","injected_mtime_ns"}}
 else: raise SystemExit(2)
 if set(value)!=expected or value["schema_version"]!=1 or value["path"]!=path or type(value["timer_active"]) is not bool or (value["phase"]=="holding" and any(type(value[name]) is not int for name in ("device","inode","atime_ns","mtime_ns","injected_mtime_ns"))): raise SystemExit(2)
 return value
def adapter(expect_success):
 subprocess.run(["/usr/bin/systemctl","reset-failed","observability-agent-health-adapter.service"],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 result=subprocess.run(["/usr/bin/systemctl","start","observability-agent-health-adapter.service"],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if (result.returncode==0) is not expect_success: raise SystemExit(2)
def restore(value):
 if value["phase"]=="holding":
  info=os.stat(path,follow_symlinks=False)
  if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o640 or info.st_nlink!=1 or info.st_dev!=value["device"] or info.st_ino!=value["inode"] or info.st_mtime_ns not in (value["mtime_ns"],value["injected_mtime_ns"]): raise SystemExit(2)
  os.utime(path,ns=(value["atime_ns"],value["mtime_ns"]),follow_symlinks=False)
 if value["timer_active"]: subprocess.run(["/usr/bin/systemctl","start","vpn-watchdog.timer"],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 adapter(True); os.unlink(journal); sync_directory()
if action=="inject":
 if os.path.lexists(journal): raise SystemExit(2)
 adapter(True)
 timer_active=subprocess.run(["/usr/bin/systemctl","is-active","--quiet","vpn-watchdog.timer"],check=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 write({{"schema_version":1,"path":path,"phase":"pending","timer_active":timer_active}})
 try:
  if timer_active: subprocess.run(["/usr/bin/systemctl","stop","vpn-watchdog.timer"],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  info=os.stat(path,follow_symlinks=False)
  if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o640 or info.st_nlink!=1: raise SystemExit(2)
  injected=int((time.time()-3600)*1000000000)
  value={{"schema_version":1,"path":path,"phase":"holding","device":info.st_dev,"inode":info.st_ino,"atime_ns":info.st_atime_ns,"mtime_ns":info.st_mtime_ns,"injected_mtime_ns":injected,"timer_active":timer_active}}
  write(value)
  os.utime(path,ns=(info.st_atime_ns,injected),follow_symlinks=False); adapter(False)
 except BaseException:
  restore(read()); raise
 state="held"
else:
 if not os.path.lexists(journal): state="absent"
 else: restore(read()); state="restored"
print(json.dumps({{"schema_version":1,"state":state}},sort_keys=True))
""".encode()


def _alert_evidence_program(
    *, exact: tuple[str, ...] = (), prefixes: tuple[str, ...] = (), wait_seconds: int
) -> bytes:
    prelude = _critical_resolve_program().decode("utf-8").split("labels=", 1)[0]
    return (
        prelude
        + f"""import time
required={exact!r}; prefixes={prefixes!r}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({{}}),NoRedirect())
deadline=time.monotonic()+{wait_seconds}
while True:
 request=urllib.request.Request("http://127.0.0.1:19094/api/v2/alerts",headers={{"Authorization":"Bearer "+token.decode().strip()}},method="GET")
 with opener.open(request,timeout=5) as response: observed=json.load(response)
 active={{item.get("labels",{{}}).get("alertname") for item in observed if isinstance(item,dict) and item.get("status",{{}}).get("state") in ("active","suppressed")}}
 if all(name in active for name in required) and all(any(name.startswith(prefix) for name in active) for prefix in prefixes): break
 if time.monotonic()>=deadline: raise SystemExit(2)
 time.sleep(min(10,max(0,deadline-time.monotonic())))
print(json.dumps({{"schema_version":1,"state":"verified"}},sort_keys=True))
"""
    ).encode()


def _grouping_inhibition_program(node: str) -> bytes:
    prelude = _critical_resolve_program().decode("utf-8").split("labels=", 1)[0]
    return (
        prelude
        + f"""import datetime, time
opener=urllib.request.build_opener(urllib.request.ProxyHandler({{}}),NoRedirect())
now=datetime.datetime.now(datetime.timezone.utc)
base={{"environment":"staging","node":{node!r},"component":"backup"}}
def alert(name): return {{"labels":dict(base,alertname=name,severity="warning"),"annotations":{{"summary":"staging matrix"}},"startsAt":now.isoformat()}}
alerts=[alert("ObservabilityBackupStageFailed"),alert("ObservabilityBackupEvidenceStale")]
def send(values):
 request=urllib.request.Request("http://127.0.0.1:19094/api/v2/alerts",data=json.dumps(values).encode(),headers={{"Authorization":"Bearer "+token.decode().strip(),"Content-Type":"application/json"}},method="POST")
 with opener.open(request,timeout=5) as response:
  if response.status not in (200,202): raise SystemExit(2)
send(alerts); time.sleep(35)
def observed():
 request=urllib.request.Request("http://127.0.0.1:19094/api/v2/alerts",headers={{"Authorization":"Bearer "+token.decode().strip()}},method="GET")
 with opener.open(request,timeout=5) as response: return json.load(response)
first={{item["labels"]["alertname"]:item for item in observed() if item.get("labels",{{}}).get("alertname") in {{"ObservabilityBackupStageFailed","ObservabilityBackupEvidenceStale"}}}}
if set(first)!={{"ObservabilityBackupStageFailed","ObservabilityBackupEvidenceStale"}} or first["ObservabilityBackupStageFailed"].get("status",{{}}).get("state")!="active" or first["ObservabilityBackupEvidenceStale"].get("status",{{}}).get("state")!="suppressed": raise SystemExit(2)
fingerprints={{name:item.get("fingerprint") for name,item in first.items()}}
for item in alerts: item["annotations"]["summary"]="staging matrix update"
send(alerts); time.sleep(2)
second={{item["labels"]["alertname"]:item for item in observed() if item.get("labels",{{}}).get("alertname") in fingerprints}}
if {{name:item.get("fingerprint") for name,item in second.items()}}!=fingerprints: raise SystemExit(2)
for item in alerts: item["endsAt"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
send(alerts)
print(json.dumps({{"schema_version":1,"state":"verified"}},sort_keys=True))
"""
    ).encode()


def _silence_owner(manifest: dict[str, Any]) -> str:
    value, _ = _private_json(
        Path(manifest["inputs"]["silence_owner"]), "silence owner rejected"
    )
    owner = value.get("owner")
    if (
        set(value) != {"schema_version", "owner"}
        or value.get("schema_version") != 1
        or not isinstance(owner, str)
        or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", owner)
    ):
        raise AcceptanceError("silence owner rejected")
    return owner


def _silence_binding(approval: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(approval)).hexdigest()[:16]


def _finite_silence_support(owner: str, node: str, binding: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", owner):
        raise AcceptanceError("silence owner rejected")
    if not re.fullmatch(r"[0-9a-f]{16}", binding):
        raise AcceptanceError("silence binding rejected")
    return f"""import datetime, json, os, pwd, re, stat, time, urllib.error, urllib.request
from uuid import UUID
owner={owner!r}; node={node!r}; reason={('staging-finite-' + binding)!r}
def token(name):
 root="/etc/observability-control-plane/credentials"; directory=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for part in root.strip("/").split("/"):
   child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory); os.close(directory); directory=child
  descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
  try: info=os.fstat(descriptor); raw=os.read(descriptor,66)
  finally: os.close(descriptor)
 finally: os.close(directory)
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or not re.fullmatch(b"[0-9a-f]{{64}}\\n?",raw): raise SystemExit(2)
 return raw.decode().strip()
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl): raise RuntimeError
opener=urllib.request.build_opener(urllib.request.ProxyHandler({{}}),NoRedirect())
sender=token("silence-sender-token"); owner_token=token("silence-owner-"+owner+"-token")
def request(path,credential,body=None,method="GET",expected=(200,)):
 value=urllib.request.Request("http://127.0.0.1:19094"+path,data=None if body is None else json.dumps(body).encode(),headers={{"Authorization":"Bearer "+credential,"Content-Type":"application/json"}},method=method)
 try:
  with opener.open(value,timeout=5) as response:
   if response.status not in expected: raise SystemExit(2)
   raw=response.read(4097); return json.loads(raw) if raw else None
 except urllib.error.HTTPError as exc:
  exc.read(4097)
  if exc.code not in expected: raise
  return exc.code
def gateway_silences():
 directory="/var/lib/observability-silence-gateway"; path=directory+"/silences.json"; uid=pwd.getpwnam("observability-silence").pw_uid
 info=os.stat(directory,follow_symlinks=False)
 if not stat.S_ISDIR(info.st_mode) or info.st_uid!=uid or stat.S_IMODE(info.st_mode)!=0o700: raise SystemExit(2)
 if not os.path.lexists(path): return {{}}
 descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(descriptor,"rb") as stream:
  info=os.fstat(stream.fileno()); raw=stream.read(1048577)
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=uid or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or len(raw)>1048576: raise SystemExit(2)
 value=json.loads(raw)
 if set(value)!={{"schema_version","silences","audit"}} or value["schema_version"]!=1 or not isinstance(value["silences"],dict) or not isinstance(value["audit"],list): raise SystemExit(2)
 for identifier,row in value["silences"].items():
  if str(UUID(identifier))!=identifier or set(row)!={{"owner","expires_at","scope","reason"}} or not isinstance(row["scope"],dict): raise SystemExit(2)
 return value["silences"]
scope={{"environment":"staging","node":node}}
def owned_ids():
 return sorted(identifier for identifier,row in gateway_silences().items() if row["owner"]==owner and row["reason"]==reason and row["scope"]==scope)
def cleanup():
 for _ in range(3):
  identifiers=owned_ids()
  if not identifiers: return
  for identifier in identifiers: request("/v1/silences/"+identifier,owner_token,None,"DELETE",(200,403))
 if owned_ids(): raise SystemExit(2)
def silence(end,matchers):
 now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
 return {{"schema_version":1,"reason":reason,"starts_at":now.strftime("%Y-%m-%dT%H:%M:%SZ"),"ends_at":end.strftime("%Y-%m-%dT%H:%M:%SZ"),"matchers":matchers}}
def resolve():
 now=datetime.datetime.now(datetime.timezone.utc).isoformat(); alert={{"labels":{{"alertname":"ObservabilityStagingSilenceMatrix","environment":"staging","node":node,"component":"control-plane","severity":"warning"}},"annotations":{{"summary":"staging finite silence"}},"startsAt":now,"endsAt":now}}
 request("/api/v2/alerts",sender,[alert],"POST",(200,202))
"""


def _finite_silence_program(owner: str, node: str, binding: str) -> bytes:
    return (
        _finite_silence_support(owner, node, binding)
        + """cleanup()
now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0); labels={"alertname":"ObservabilityStagingSilenceMatrix","environment":"staging","node":node,"component":"control-plane","severity":"warning"}
active=silence(now+datetime.timedelta(seconds=70),scope)
created=request("/v1/silences",owner_token,active,"POST",(201,)); identifier=created["silence_id"]
alert={"labels":labels,"annotations":{"summary":"staging finite silence"},"startsAt":now.isoformat()}
try:
 request("/api/v2/alerts",sender,[alert],"POST",(200,202)); time.sleep(35)
 observed=request("/api/v2/alerts",sender)
 match=[item for item in observed if item.get("labels",{}).get("alertname")==labels["alertname"]]
 if len(match)!=1 or match[0].get("status",{}).get("state")!="suppressed": raise SystemExit(2)
 time.sleep(40); observed=request("/api/v2/alerts",sender)
 match=[item for item in observed if item.get("labels",{}).get("alertname")==labels["alertname"]]
 if len(match)!=1 or match[0].get("status",{}).get("state")!="active": raise SystemExit(2)
 request("/v1/silences/"+identifier,owner_token,None,"DELETE",(403,))
 second=request("/v1/silences",owner_token,silence(now+datetime.timedelta(seconds=300),scope),"POST",(201,))["silence_id"]
 request("/v1/silences/"+second,owner_token,None,"DELETE",(200,))
 request("/v1/silences",owner_token,silence(now+datetime.timedelta(seconds=20000),scope),"POST",(400,))
 request("/v1/silences",owner_token,silence(now+datetime.timedelta(seconds=300),{"environment":"staging"}),"POST",(400,))
 request("/v1/silences",owner_token,silence(now+datetime.timedelta(seconds=300),{"environment":"staging","node":node,"unknown":"value"}),"POST",(400,))
 request("/v1/silences",sender,silence(now+datetime.timedelta(seconds=300),scope),"POST",(403,))
finally:
 try: resolve()
 finally: cleanup()
print(json.dumps({"schema_version":1,"state":"verified"},sort_keys=True))
"""
    ).encode()


def _finite_silence_restore_program(owner: str, node: str, binding: str) -> bytes:
    return (
        _finite_silence_support(owner, node, binding)
        + """cleanup(); resolve()
print(json.dumps({"schema_version":1,"state":"restored"},sort_keys=True))
"""
    ).encode()


def _matrix_resolve_program(node: str) -> bytes:
    prelude = _critical_resolve_program().decode("utf-8").split("labels=", 1)[0]
    return (
        prelude
        + f"""import datetime
names=("ObservabilityBackupStageFailed","ObservabilityBackupEvidenceStale","ObservabilityStagingSilenceMatrix")
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
alerts=[]
for name in names:
 component="backup" if name.startswith("ObservabilityBackup") else "control-plane"
 alerts.append({{"labels":{{"alertname":name,"environment":"staging","node":{node!r},"component":component,"severity":"warning"}},"annotations":{{"summary":"staging matrix"}},"startsAt":now,"endsAt":now}})
request=urllib.request.Request("http://127.0.0.1:19094/api/v2/alerts",data=json.dumps(alerts).encode(),headers={{"Authorization":"Bearer "+token.decode().strip(),"Content-Type":"application/json"}},method="POST")
with urllib.request.build_opener(urllib.request.ProxyHandler({{}}),NoRedirect()).open(request,timeout=5) as response:
 if response.status not in (200,202): raise SystemExit(2)
print(json.dumps({{"schema_version":1,"state":"resolved"}},sort_keys=True))
"""
    ).encode()


def _service_fault_program(units: tuple[str, ...], wait_seconds: int) -> bytes:
    return (
        "import json, subprocess, time\n"
        f"units={units!r}\n"
        "active=[]\n"
        "for unit in units:\n"
        " r=subprocess.run(['/usr/bin/systemctl','is-active','--quiet',unit],check=False); active.append(r.returncode==0)\n"
        "try:\n"
        " subprocess.run(['/usr/bin/systemctl','stop',*units],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        f" time.sleep({wait_seconds})\n"
        "finally:\n"
        " restore=[unit for unit,was_active in zip(units,active) if was_active]\n"
        " if restore: subprocess.run(['/usr/bin/systemctl','start',*restore],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "print(json.dumps({'schema_version':1,'state':'restored'}))\n"
    ).encode()


def _unit_action_program(action: str, units: tuple[str, ...]) -> bytes:
    if action not in {"start", "stop"}:
        raise AcceptanceError("unit action rejected")
    return (
        "import json, subprocess\n"
        f"units={units!r}\n"
        f"action={action!r}\n"
        "subprocess.run(['/usr/bin/systemctl',action,*units],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "expected='active' if action == 'start' else 'inactive'\n"
        "for unit in units:\n"
        " result=subprocess.run(['/usr/bin/systemctl','is-active',unit],check=False,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)\n"
        " if (action == 'start' and (result.returncode != 0 or result.stdout.strip() != expected)) or (action == 'stop' and result.returncode == 0): raise SystemExit(2)\n"
        "print(json.dumps({'schema_version':1,'state':action+'ed'}))\n"
    ).encode()


def _deadman_evidence_program(
    *, incident: bool, delivery: str, wait_seconds: int, require_advancing: bool
) -> bytes:
    if delivery not in {"firing", "recovery"}:
        raise AcceptanceError("deadman evidence rejected")
    return f"""import json, time, urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({{}}))
def status():
    with opener.open("http://127.0.0.1:19094/v1/status",timeout=5) as response:
        raw=response.read(4097)
    value=json.loads(raw)
    if len(raw)>4096 or set(value)!={{"schema","incident","last_delivery","last_pulse","last_canary_delivery"}} or value.get("schema")!=1:
        raise RuntimeError("status rejected")
    return value
deadline=time.monotonic()+{wait_seconds}
while True:
    value=status()
    if value.get("incident") is {incident!r} and value.get("last_delivery")=={delivery!r}:
        break
    if time.monotonic()>=deadline: raise SystemExit(2)
    time.sleep(min(10,max(0,deadline-time.monotonic())))
if {require_advancing!r}:
    first=value["last_pulse"]
    time.sleep(65)
    second=status()
    if second.get("incident") is not False or second.get("last_delivery")!="recovery" or second["last_pulse"]<=first:
        raise SystemExit(2)
print(json.dumps({{"schema_version":1,"state":"verified"}},sort_keys=True))
""".encode()


def _primary_alert_evidence_program(
    alertname: str, *, active: bool, wait_seconds: int
) -> bytes:
    if not SLUG.fullmatch(alertname.replace("_", "-")) and not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9]{1,127}", alertname
    ):
        raise AcceptanceError("primary alert evidence rejected")
    prelude = _critical_resolve_program().decode("utf-8").split("labels={", 1)[0]
    return (prelude + f"""import time
opener=urllib.request.build_opener(urllib.request.ProxyHandler({{}}),NoRedirect())
deadline=time.monotonic()+{wait_seconds}
while True:
    request=urllib.request.Request("http://127.0.0.1:19094/api/v2/alerts",headers={{"Authorization":"Bearer "+token.decode().strip()}},method="GET")
    with opener.open(request,timeout=5) as response:
        observed=json.load(response)
    matches=[item for item in observed if isinstance(item,dict) and item.get("labels",{{}}).get("alertname")=={alertname!r} and item.get("status",{{}}).get("state")=="active" and item.get("receivers")==[{{"name":"telegram-primary"}}]]
    if bool(matches) is {active!r}: break
    if time.monotonic()>=deadline: raise SystemExit(2)
    time.sleep(min(10,max(0,deadline-time.monotonic())))
print(json.dumps({{"schema_version":1,"state":"verified"}},sort_keys=True))
""").encode()


def _critical_lifecycle_program(wait_seconds: int = 3700) -> bytes:
    """Return the fixed one-hour primary-route lifecycle payload."""
    return f"""import datetime
import json
import os
import re
import stat
import time
import urllib.request

def read_token():
    root = "/etc/observability-control-plane/credentials"
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in root.strip("/").split("/"):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            metadata = os.fstat(directory)
            if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                raise RuntimeError("gateway credential unavailable")
        descriptor = os.open("silence-sender-token", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            metadata = os.fstat(descriptor)
            raw = os.read(descriptor, 66)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1
                or metadata.st_size not in (64, 65)
                or not re.fullmatch(b"[0-9a-f]{{64}}\\n?", raw)):
                raise RuntimeError("gateway credential unavailable")
            return raw.decode("ascii").rstrip("\\n")
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("gateway redirect rejected")

token = read_token()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({{}}), NoRedirect())
def request(path, data=None, method="GET"):
    value = urllib.request.Request("http://127.0.0.1:19094" + path, data=data,
        headers={{"Authorization":"Bearer " + token,"Content-Type":"application/json"}}, method=method)
    return opener.open(value, timeout=5)

now = datetime.datetime.now(datetime.timezone.utc)
labels = {{"alertname":"ObservabilityStagingCriticalLifecycle","component":"control-plane","environment":"staging","severity":"critical"}}
alert = {{"labels":labels,"annotations":{{"summary":"staging critical lifecycle","runbook":"docs/OBSERVABILITY-OPERATIONS.md"}},"startsAt":now.isoformat()}}
def send(value):
    with request("/api/v2/alerts", data=json.dumps([value]).encode("utf-8"), method="POST") as response:
        if response.status not in (200, 202):
            raise RuntimeError("delivery rejected")
send(alert)
fingerprint = json.dumps(labels, sort_keys=True, separators=(",", ":"))
deadline = time.monotonic() + {wait_seconds}
while True:
    with request("/api/v2/alerts") as response:
        observed = json.load(response)
    if not isinstance(observed, list) or not any(
        isinstance(item, dict)
        and json.dumps(item.get("labels"), sort_keys=True, separators=(",", ":")) == fingerprint
        and item.get("status", {{}}).get("state") == "active"
        and item.get("receivers") == [{{"name":"telegram-primary"}}]
        for item in observed
    ):
        raise RuntimeError("receiver routing evidence missing")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        break
    time.sleep(min(30, remaining))
resolved = dict(alert)
resolved["endsAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
send(resolved)
print(json.dumps({{"schema_version":1,"receiver":"telegram-primary","state":"resolved"}}, sort_keys=True))
""".encode("utf-8")


def _critical_resolve_program() -> bytes:
    return b"""import datetime, json, os, re, stat, urllib.request
directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for part in "etc/observability-control-plane/credentials".split("/"):
        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
        os.close(directory); directory = child
        metadata = os.fstat(directory)
        if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022: raise SystemExit(2)
    descriptor = os.open("silence-sender-token", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    metadata = os.fstat(descriptor); token = os.read(descriptor, 66)
    os.close(descriptor)
finally:
    os.close(directory)
if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != 0o600
    or metadata.st_nlink != 1 or metadata.st_size not in (64,65) or not re.fullmatch(b"[0-9a-f]{64}\\n?", token)):
    raise SystemExit(2)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): raise RuntimeError
labels={"alertname":"ObservabilityStagingCriticalLifecycle","component":"control-plane","environment":"staging","severity":"critical"}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
alert={"labels":labels,"annotations":{"summary":"staging critical lifecycle","runbook":"docs/OBSERVABILITY-OPERATIONS.md"},"startsAt":now,"endsAt":now}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
request=urllib.request.Request("http://127.0.0.1:19094/api/v2/alerts",data=json.dumps([alert]).encode(),headers={"Authorization":"Bearer "+token.decode().strip(),"Content-Type":"application/json"},method="POST")
with opener.open(request,timeout=5) as response:
    if response.status not in (200,202): raise SystemExit(2)
print(json.dumps({"schema_version":1,"state":"resolved"}))
"""


def _start_units_program(units: tuple[str, ...]) -> bytes:
    return (
        "import json, subprocess\n"
        f"units={units!r}\n"
        "subprocess.run(['/usr/bin/systemctl','start',*units],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "print(json.dumps({'schema_version':1,'state':'started'}))\n"
    ).encode()


def _primary_canary_program(expect_success: bool) -> bytes:
    return (
        "import json, subprocess\n"
        "subprocess.run(['/usr/bin/systemctl','reset-failed','observability-primary-canary.service'],check=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "result=subprocess.run(['/usr/bin/systemctl','start','observability-primary-canary.service'],check=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        f"expected={expect_success!r}\n"
        "if (result.returncode == 0) != expected: raise SystemExit(2)\n"
        "print(json.dumps({'schema_version':1,'state':'succeeded' if expected else 'failed'}))\n"
    ).encode()


def _expect_remote_verified(raw: bytes, category: str) -> None:
    try:
        if json.loads(raw) != {"schema_version": 1, "state": "verified"}:
            raise ValueError
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise AcceptanceError(category) from None


def _require_healthy(manifest: dict[str, Any], component: str) -> None:
    value = _operator(manifest, "status", component)
    if value.get("state") != "healthy":
        raise AcceptanceError("component recovery rejected")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AcceptanceError("provider redirect rejected")


def _hetzner_action(manifest: dict[str, Any], action: str) -> None:
    binding, _ = _private_json(
        Path(manifest["inputs"]["hetzner_binding"]), "provider binding rejected"
    )
    if (
        set(binding)
        != {
            "schema_version",
            "provider",
            "environment",
            "account_id",
            "state_sha256",
            "terraform_address",
            "server_id",
        }
        or binding.get("schema_version") != 1
        or binding.get("provider") != "hetzner"
        or binding.get("environment") != "staging"
        or not HEX64.fullmatch(str(binding.get("account_id", "")))
        or not HEX64.fullmatch(str(binding.get("state_sha256", "")))
        or binding.get("terraform_address") != "hcloud_server.vpn"
        or not isinstance(binding.get("server_id"), int)
        or binding["server_id"] <= 0
    ):
        raise AcceptanceError("provider binding rejected")
    token = os.environ.get("HCLOUD_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{20,256}", token):
        raise AcceptanceError("Hetzner authority unavailable")
    account_id = hashlib.sha256(
        b"hcloud-account-binding\0" + token.encode()
    ).hexdigest()
    if not hmac.compare_digest(account_id, binding["account_id"]):
        raise AcceptanceError("provider binding rejected")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TF_PLUGIN_CACHE_DIR",
            "HCLOUD_TOKEN",
        }
    }
    environment.update(
        {
            "PROVIDER": "hetzner",
            "ENV": "staging",
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
        }
    )
    try:
        state_result = subprocess.run(
            [str(ROOT / "scripts" / "terraform-env.sh"), "state", "pull"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        state_raw = state_result.stdout
        if len(state_raw) > 16 * 1024 * 1024 or not hmac.compare_digest(
            hashlib.sha256(state_raw).hexdigest(), binding["state_sha256"]
        ):
            raise AcceptanceError("provider binding rejected")
        state = json.loads(state_raw)
        resources = state.get("resources") if isinstance(state, dict) else None
        matches = (
            [
                resource
                for resource in resources
                if isinstance(resource, dict)
                and resource.get("mode") == "managed"
                and resource.get("type") == "hcloud_server"
                and resource.get("name") == "vpn"
            ]
            if isinstance(resources, list)
            else []
        )
        instances = matches[0].get("instances") if len(matches) == 1 else None
        attributes = (
            instances[0].get("attributes")
            if isinstance(instances, list)
            and len(instances) == 1
            and isinstance(instances[0], dict)
            else None
        )
        observed_id = attributes.get("id") if isinstance(attributes, dict) else None
        if str(observed_id) != str(binding["server_id"]):
            raise AcceptanceError("provider binding rejected")
    except AcceptanceError:
        raise
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        raise AcceptanceError("provider binding rejected") from None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    base = f"https://api.hetzner.cloud/v1/servers/{binding['server_id']}/actions/"
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if action not in {"poweroff", "poweron"}:
        raise AcceptanceError("provider action rejected")
    try:
        request = urllib.request.Request(
            base + action, data=b"{}", headers=headers, method="POST"
        )
        with opener.open(request, timeout=15) as response:
            raw = response.read(4097)
            if response.status not in (200, 201) or len(raw) > 4096:
                raise AcceptanceError("provider action failed")
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        raise AcceptanceError("provider action failed") from None


def _hetzner_power_cycle(manifest: dict[str, Any], wait_seconds: int) -> None:
    _hetzner_action(manifest, "poweroff")
    try:
        time.sleep(wait_seconds)
    finally:
        _hetzner_action(manifest, "poweron")


def _token_rejected(path: Path) -> bool:
    raw, _ = _private_file(path, "old token rejected")
    try:
        token = raw.decode("ascii", "strict").strip()
    except UnicodeError:
        raise AcceptanceError("old token rejected") from None
    if not re.fullmatch(r"[0-9]{4,16}:[A-Za-z0-9_-]{10,256}", token):
        raise AcceptanceError("old token rejected")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/getMe", method="GET"
    )
    try:
        with opener.open(request, timeout=10) as response:
            response.read(4097)
        return False
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            exc.read(4097)
            return True
        raise AcceptanceError("old token rejection unavailable") from None
    except (OSError, UnicodeError, urllib.error.URLError):
        raise AcceptanceError("old token rejection unavailable") from None


def _old_sender_generation(manifest: dict[str, Any]) -> str:
    value, _ = _private_json(
        Path(manifest["inputs"]["canary_old_generation"]),
        "old sender generation rejected",
    )
    generation = value.get("generation")
    if (
        set(value) != {"schema_version", "generation"}
        or value.get("schema_version") != 1
        or not isinstance(generation, str)
        or not HEX64.fullmatch(generation)
    ):
        raise AcceptanceError("old sender generation rejected")
    return generation


def _old_sender_rejection_program(generation: str) -> bytes:
    return f"""import json, os, re, socket, ssl, stat
from urllib.parse import urlsplit
root="/etc/observability-agent/credentials"; generation={generation!r}; directory=os.path.join(root,"generations",generation)
if os.path.realpath(directory)!=directory or not os.path.isdir(directory): raise SystemExit(2)
for name,mode in (("prometheus.yml",0o644),("receiver-ca.crt",0o600),("client.crt",0o600),("client.key",0o600)):
 path=os.path.join(directory,name); info=os.stat(path,follow_symlinks=False)
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=mode or info.st_nlink!=1: raise SystemExit(2)
config=open(os.path.join(directory,"prometheus.yml"),encoding="utf-8").read(65537)
urls=re.findall(r'^\\s*- url: "(https://[^"\\s]+)"$',config,re.M); snis=re.findall(r'^\\s*server_name: "([^"\\s]+)"$',config,re.M)
if len(urls)!=1 or len(snis)!=1: raise SystemExit(2)
parsed=urlsplit(urls[0]); sock=socket.create_connection((parsed.hostname,parsed.port or 443),timeout=5)
try:
 context=ssl.create_default_context(cafile=os.path.join(directory,"receiver-ca.crt")); context.load_cert_chain(os.path.join(directory,"client.crt"),os.path.join(directory,"client.key"))
 try: context.wrap_socket(sock,server_hostname=snis[0])
 except ssl.SSLError: rejected=True
 else: rejected=False
finally: sock.close()
if not rejected: raise SystemExit(2)
print(json.dumps({{"schema_version":1,"state":"rejected"}},sort_keys=True))
""".encode()


def _rollback_generation(manifest: dict[str, Any]) -> str:
    value, _ = _private_json(
        Path(manifest["inputs"]["rollback_manifest"]),
        "rollback manifest rejected",
    )
    generation = value.get("previous_generation")
    if (
        set(value)
        != {
            "schema_version",
            "host",
            "component",
            "previous_generation",
            "vars_sha256",
            "secrets_sha256",
        }
        or value.get("schema_version") != 1
        or value.get("host") != manifest["hosts"]["control-plane"]
        or value.get("component") != "control-plane"
        or not isinstance(generation, str)
        or not HEX64.fullmatch(generation)
        or not HEX64.fullmatch(str(value.get("vars_sha256", "")))
        or not HEX64.fullmatch(str(value.get("secrets_sha256", "")))
    ):
        raise AcceptanceError("rollback manifest rejected")
    return generation


def _invalid_candidate_vars(manifest: dict[str, Any]) -> str:
    path = manifest["inputs"]["invalid_control_plane_vars"]
    category = "invalid candidate rejected"
    try:
        invalid_raw, _ = _private_file(Path(path), category)
        candidate_raw, _ = _private_file(
            Path(manifest["inputs"]["candidate_control_plane_vars"]), category
        )
        invalid = yaml.safe_load(invalid_raw.decode("utf-8"))
        candidate = yaml.safe_load(candidate_raw.decode("utf-8"))
        candidate_role = candidate["observability_control_plane"]
        expected = copy.deepcopy(candidate)
        expected_role = expected["observability_control_plane"]
        expected_role["prometheus_listen"] = "0.0.0.0:9090"
        if (
            not isinstance(candidate, dict)
            or not isinstance(invalid, dict)
            or not isinstance(candidate_role, dict)
            or candidate_role.get("enabled") is not True
            or candidate_role.get("prometheus_listen") != "127.0.0.1:9090"
            or invalid != expected
        ):
            raise ValueError
    except (
        AcceptanceError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        yaml.YAMLError,
    ):
        raise AcceptanceError("invalid candidate rejected") from None
    return path


def _control_plane_generation_program() -> bytes:
    return b"""import json, os, re, stat, subprocess
root="/etc/observability-control-plane"; pattern=re.compile(r"^[0-9a-f]{64}[.]yml$")
def generation(name,required):
 path=os.path.join(root,name)
 if not os.path.islink(path):
  if required: raise SystemExit(2)
  return None
 resolved=os.path.realpath(path); parent=os.path.join(root,"generations")
 if os.path.dirname(resolved)!=parent or not pattern.fullmatch(os.path.basename(resolved)): raise SystemExit(2)
 info=os.stat(resolved,follow_symlinks=False)
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1: raise SystemExit(2)
 return os.path.basename(resolved).removesuffix(".yml")
current=generation("current.yml",True); previous=generation("previous.yml",False)
data=os.stat("/var/lib/observability-prometheus",follow_symlinks=False)
if not stat.S_ISDIR(data.st_mode): raise SystemExit(2)
result=subprocess.run(["/usr/bin/systemctl","list-units","--all","--plain","--no-legend","observability-*.timer"],check=False,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
if result.returncode!=0: raise SystemExit(2)
names=[line.split()[0] for line in result.stdout.splitlines() if line.split()]
if len(names)!=len(set(names)): raise SystemExit(2)
print(json.dumps({"schema_version":1,"state":"verified","current":current,"previous":previous,"tsdb_device":data.st_dev,"tsdb_inode":data.st_ino,"schedule_count":len(names)},sort_keys=True))
"""


def _generation_state(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw)
        if (
            set(value)
            != {
                "schema_version",
                "state",
                "current",
                "previous",
                "tsdb_device",
                "tsdb_inode",
                "schedule_count",
            }
            or value.get("schema_version") != 1
            or value.get("state") != "verified"
            or not HEX64.fullmatch(str(value.get("current", "")))
            or (
                value.get("previous") is not None
                and not HEX64.fullmatch(str(value["previous"]))
            )
            or any(
                not isinstance(value.get(name), int) or value[name] < 0
                for name in ("tsdb_device", "tsdb_inode", "schedule_count")
            )
        ):
            raise ValueError
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise AcceptanceError("control-plane generation evidence rejected") from None
    return value


def _default_execute(
    step: str, manifest: dict[str, Any], approval: dict[str, Any]
) -> str:
    deadline = approval["deadline_seconds"]
    if step == "fresh-metrics":
        raw = _remote(manifest, "control-plane", _metrics_program(), deadline)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("fresh metrics unavailable")
    elif step == "ingestion-negative":
        raw = _remote(manifest, "canary", _ingestion_negative_program(), deadline)
        _expect_remote_verified(raw, "ingestion negative matrix rejected")
        raw = _remote(manifest, "control-plane", _metrics_program(), 130)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("ingestion recovery rejected")
    elif step == "agent-wal":
        _require_healthy(manifest, "agent")
        _require_healthy(manifest, "control-plane")
        baseline = _wal_sample(
            _remote(manifest, "canary", _wal_metrics_program(), 30)
        )
        _remote(
            manifest,
            "control-plane",
            _unit_action_program("stop", ("nginx.service",)),
            60,
        )
        try:
            time.sleep(65)
            outage = _wal_sample(
                _remote(manifest, "canary", _wal_metrics_program(), 30)
            )
        finally:
            _remote(
                manifest,
                "control-plane",
                _unit_action_program("start", ("nginx.service",)),
                60,
            )
        lag = (
            outage["prometheus_remote_storage_queue_highest_timestamp_seconds"]
            - outage[
                "prometheus_remote_storage_queue_highest_sent_timestamp_seconds"
            ]
        )
        if (
            lag < 0
            or lag > 3600
            or outage["prometheus_remote_storage_samples_dropped_total"]
            != baseline["prometheus_remote_storage_samples_dropped_total"]
            or not (
                outage["prometheus_remote_storage_samples_pending"]
                > baseline["prometheus_remote_storage_samples_pending"]
                or outage["prometheus_remote_storage_samples_failed_total"]
                > baseline["prometheus_remote_storage_samples_failed_total"]
                or outage["prometheus_remote_storage_samples_retried_total"]
                > baseline["prometheus_remote_storage_samples_retried_total"]
                or lag > 0
            )
        ):
            raise AcceptanceError("agent WAL outage evidence rejected")
        recovery_deadline = time.monotonic() + 180
        while True:
            recovered = _wal_sample(
                _remote(manifest, "canary", _wal_metrics_program(), 30)
            )
            recovery_lag = (
                recovered[
                    "prometheus_remote_storage_queue_highest_timestamp_seconds"
                ]
                - recovered[
                    "prometheus_remote_storage_queue_highest_sent_timestamp_seconds"
                ]
            )
            if (
                0 <= recovery_lag <= 60
                and recovered[
                    "prometheus_remote_storage_queue_highest_sent_timestamp_seconds"
                ]
                > baseline[
                    "prometheus_remote_storage_queue_highest_sent_timestamp_seconds"
                ]
            ):
                break
            if time.monotonic() >= recovery_deadline:
                raise AcceptanceError("agent WAL recovery rejected")
            time.sleep(10)
        raw = _remote(manifest, "control-plane", _metrics_program(), 130)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("agent WAL delivery recovery rejected")
    elif step == "staleness":
        _require_healthy(manifest, "agent")
        _require_healthy(manifest, "control-plane")
        raw = _remote(manifest, "canary", _stale_producer_program("inject"), 60)
        if json.loads(raw) != {"schema_version": 1, "state": "held"}:
            raise AcceptanceError("stale producer fault rejected")
        try:
            raw = _remote(
                manifest,
                "control-plane",
                _alert_evidence_program(
                    exact=("ObservabilityWatchdogEvidenceStale",),
                    wait_seconds=300,
                ),
                330,
            )
            _expect_remote_verified(raw, "stale producer evidence rejected")
        finally:
            restored = _remote(
                manifest, "canary", _stale_producer_program("restore"), 60
            )
            if json.loads(restored) != {"schema_version": 1, "state": "restored"}:
                raise AcceptanceError("stale producer restoration rejected")
        _remote(
            manifest,
            "canary",
            _unit_action_program("stop", ("observability-agent.service",)),
            60,
        )
        try:
            raw = _remote(
                manifest,
                "control-plane",
                _alert_evidence_program(
                    exact=("ObservabilityExpectedTargetMissing",),
                    prefixes=("ObservabilityRequiredFamilyMissing_",),
                    wait_seconds=600,
                ),
                630,
            )
            _expect_remote_verified(raw, "missing target evidence rejected")
        finally:
            _remote(
                manifest,
                "canary",
                _unit_action_program("start", ("observability-agent.service",)),
                60,
            )
        raw = _remote(manifest, "control-plane", _metrics_program(), 130)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("staleness recovery rejected")
    elif step == "grouping-inhibition":
        raw = _remote(
            manifest,
            "control-plane",
            _grouping_inhibition_program(manifest["hosts"]["canary"]),
            deadline,
        )
        _expect_remote_verified(raw, "grouping and inhibition evidence rejected")
    elif step == "finite-silence":
        raw = _remote(
            manifest,
            "control-plane",
            _finite_silence_program(
                _silence_owner(manifest),
                manifest["hosts"]["canary"],
                _silence_binding(approval),
            ),
            deadline,
        )
        _expect_remote_verified(raw, "finite silence evidence rejected")
    elif step == "primary-lifecycle":
        raw = _remote(
            manifest, "control-plane", _critical_lifecycle_program(), deadline
        )
        value = json.loads(raw)
        if value != {
            "schema_version": 1,
            "receiver": "telegram-primary",
            "state": "resolved",
        }:
            raise AcceptanceError("critical lifecycle result rejected")
    elif step == "deadman-lifecycle":
        _require_healthy(manifest, "control-plane")
        _require_healthy(manifest, "deadman")
        _remote(
            manifest,
            "control-plane",
            _unit_action_program("stop", ("observability-deadman-pulse.timer",)),
            deadline,
        )
        time.sleep(3700)
        raw = _remote(
            manifest,
            "deadman",
            _deadman_evidence_program(
                incident=True,
                delivery="firing",
                wait_seconds=60,
                require_advancing=False,
            ),
            90,
        )
        _expect_remote_verified(raw, "deadman firing evidence rejected")
        _remote(
            manifest,
            "control-plane",
            _unit_action_program("start", ("observability-deadman-pulse.timer",)),
            deadline,
        )
        raw = _remote(
            manifest,
            "deadman",
            _deadman_evidence_program(
                incident=False,
                delivery="recovery",
                wait_seconds=300,
                require_advancing=True,
            ),
            390,
        )
        _expect_remote_verified(raw, "deadman recovery evidence rejected")
    elif step == "control-service-loss":
        _require_healthy(manifest, "control-plane")
        _require_healthy(manifest, "deadman")
        units = (
            "observability-prometheus.service",
            "observability-alertmanager.service",
            "observability-deadman-pulse.timer",
        )
        _remote(
            manifest, "control-plane", _unit_action_program("stop", units), deadline
        )
        raw = _remote(
            manifest,
            "deadman",
            _deadman_evidence_program(
                incident=True,
                delivery="firing",
                wait_seconds=600,
                require_advancing=False,
            ),
            630,
        )
        _expect_remote_verified(raw, "control service loss evidence rejected")
        _remote(
            manifest, "control-plane", _unit_action_program("start", units), deadline
        )
        raw = _remote(
            manifest,
            "deadman",
            _deadman_evidence_program(
                incident=False,
                delivery="recovery",
                wait_seconds=300,
                require_advancing=True,
            ),
            390,
        )
        _expect_remote_verified(raw, "control service recovery rejected")
        _require_healthy(manifest, "control-plane")
    elif step == "control-host-loss":
        _require_healthy(manifest, "control-plane")
        _require_healthy(manifest, "deadman")
        _hetzner_action(manifest, "poweroff")
        try:
            raw = _remote(
                manifest,
                "deadman",
                _deadman_evidence_program(
                    incident=True,
                    delivery="firing",
                    wait_seconds=600,
                    require_advancing=False,
                ),
                630,
            )
        finally:
            _hetzner_action(manifest, "poweron")
        _expect_remote_verified(raw, "control host loss evidence rejected")
        raw = _remote(
            manifest,
            "deadman",
            _deadman_evidence_program(
                incident=False,
                delivery="recovery",
                wait_seconds=600,
                require_advancing=True,
            ),
            690,
        )
        _expect_remote_verified(raw, "control host recovery rejected")
        _require_healthy(manifest, "control-plane")
    elif step == "deadman-service-loss":
        _require_healthy(manifest, "control-plane")
        _require_healthy(manifest, "deadman")
        _remote(
            manifest,
            "deadman",
            _unit_action_program("stop", ("observability-deadman.service",)),
            deadline,
        )
        raw = _remote(
            manifest,
            "control-plane",
            _primary_alert_evidence_program(
                "ObservabilityDeadmanReverseMissing", active=True, wait_seconds=600
            ),
            630,
        )
        _expect_remote_verified(raw, "deadman service loss evidence rejected")
        _remote(
            manifest,
            "deadman",
            _unit_action_program("start", ("observability-deadman.service",)),
            deadline,
        )
        raw = _remote(
            manifest,
            "control-plane",
            _primary_alert_evidence_program(
                "ObservabilityDeadmanReverseMissing", active=False, wait_seconds=300
            ),
            330,
        )
        _expect_remote_verified(raw, "deadman service recovery rejected")
        _require_healthy(manifest, "deadman")
    elif step == "primary-authority-loss":
        raw = _remote(
            manifest,
            "control-plane",
            _primary_canary_program(False),
            deadline,
        )
        if json.loads(raw) != {"schema_version": 1, "state": "failed"}:
            raise AcceptanceError("primary authority loss result rejected")
        raw = _remote(
            manifest,
            "deadman",
            _deadman_evidence_program(
                incident=True,
                delivery="firing",
                wait_seconds=600,
                require_advancing=False,
            ),
            630,
        )
        _expect_remote_verified(raw, "primary authority loss evidence rejected")
        _operator(manifest, "rotate", "control-plane", confirm=True)
        raw = _remote(
            manifest,
            "control-plane",
            _primary_canary_program(True),
            deadline,
        )
        if json.loads(raw) != {"schema_version": 1, "state": "succeeded"}:
            raise AcceptanceError("primary authority recovery rejected")
        raw = _remote(
            manifest,
            "deadman",
            _deadman_evidence_program(
                incident=False,
                delivery="recovery",
                wait_seconds=300,
                require_advancing=True,
            ),
            390,
        )
        _expect_remote_verified(raw, "primary authority recovery rejected")
        _require_healthy(manifest, "control-plane")
    elif step == "canary-sender-rotation":
        _operator(manifest, "rotate", "agent", confirm=True)
        _require_healthy(manifest, "agent")
    elif step == "primary-bot-rotation":
        _operator(manifest, "rotate", "control-plane", confirm=True)
        _require_healthy(manifest, "control-plane")
        raw = _remote(manifest, "control-plane", _metrics_program(), 130)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("primary rotation freshness rejected")
    elif step == "secondary-bot-rotation":
        _operator(manifest, "rotate", "deadman", confirm=True)
        _require_healthy(manifest, "deadman")
    elif step == "old-material-rejection":
        old_sender = _remote(
            manifest,
            "canary",
            _old_sender_rejection_program(_old_sender_generation(manifest)),
            deadline,
        )
        try:
            sender_rejected = json.loads(old_sender) == {
                "schema_version": 1,
                "state": "rejected",
            }
        except (UnicodeError, TypeError, json.JSONDecodeError):
            sender_rejected = False
        if not sender_rejected or not all(
            _token_rejected(Path(manifest["inputs"][name]))
            for name in ("primary_old_token", "secondary_old_token")
        ):
            raise AcceptanceError("still-valid old canary sender authority")
        raw = _remote(manifest, "control-plane", _metrics_program(), 130)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("replacement canary sender freshness rejected")
    elif step == "invalid-candidate-refusal":
        expected = _rollback_generation(manifest)
        before = _generation_state(
            _remote(manifest, "control-plane", _control_plane_generation_program(), 30)
        )
        if before["current"] != expected:
            raise AcceptanceError("invalid candidate baseline rejected")
        invalid_variables = _invalid_candidate_vars(manifest)
        rendered = _operator(
            manifest,
            "render",
            "control-plane",
            variables=manifest["inputs"]["candidate_control_plane_vars"],
            secrets=manifest["inputs"]["candidate_control_plane_secrets"],
        )
        if rendered.get("state") != "rendered-check":
            raise AcceptanceError("candidate render evidence rejected")
        refusal = _operator(
            manifest,
            "rotate",
            "control-plane",
            confirm=True,
            variables=invalid_variables,
            secrets=manifest["inputs"]["candidate_control_plane_secrets"],
            expect_role_guard_refusal=True,
        )
        if refusal.get("state") != "role-guard-refused":
            raise AcceptanceError("invalid candidate refusal evidence rejected")
        after = _generation_state(
            _remote(manifest, "control-plane", _control_plane_generation_program(), 30)
        )
        if after != before:
            raise AcceptanceError("invalid candidate changed retained state")
        _require_healthy(manifest, "control-plane")
    elif step == "valid-candidate-activation":
        expected = _rollback_generation(manifest)
        before = _generation_state(
            _remote(manifest, "control-plane", _control_plane_generation_program(), 30)
        )
        if before["current"] != expected:
            raise AcceptanceError("candidate activation baseline rejected")
        _operator(
            manifest,
            "rotate",
            "control-plane",
            confirm=True,
            variables=manifest["inputs"]["candidate_control_plane_vars"],
            secrets=manifest["inputs"]["candidate_control_plane_secrets"],
        )
        after = _generation_state(
            _remote(manifest, "control-plane", _control_plane_generation_program(), 30)
        )
        if (
            after["current"] == expected
            or after["previous"] != expected
            or after["tsdb_device"] != before["tsdb_device"]
            or after["tsdb_inode"] != before["tsdb_inode"]
            or after["schedule_count"] != before["schedule_count"]
        ):
            raise AcceptanceError("candidate activation evidence rejected")
        _require_healthy(manifest, "control-plane")
        raw = _remote(manifest, "control-plane", _metrics_program(), 130)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("candidate activation freshness rejected")
    elif step == "control-plane-rollback":
        expected = _rollback_generation(manifest)
        before = _generation_state(
            _remote(manifest, "control-plane", _control_plane_generation_program(), 30)
        )
        if before["current"] == expected or before["previous"] != expected:
            raise AcceptanceError("rollback baseline rejected")
        _operator(
            manifest,
            "rollback",
            "control-plane",
            confirm=True,
            variables=manifest["inputs"]["control_plane_vars"],
            secrets=manifest["inputs"]["control_plane_secrets"],
        )
        after = _generation_state(
            _remote(manifest, "control-plane", _control_plane_generation_program(), 30)
        )
        if (
            after["current"] != expected
            or after["tsdb_device"] != before["tsdb_device"]
            or after["tsdb_inode"] != before["tsdb_inode"]
            or after["schedule_count"] != before["schedule_count"]
        ):
            raise AcceptanceError("rollback generation evidence rejected")
        _require_healthy(manifest, "control-plane")
        raw = _remote(manifest, "control-plane", _metrics_program(), 130)
        if json.loads(raw).get("state") != "advancing":
            raise AcceptanceError("rollback freshness rejected")
    elif step == "component-removal":
        for component in ("agent", "control-plane", "deadman"):
            _operator(manifest, "remove", component, confirm=True)
    else:  # pragma: no cover
        raise AcceptanceError("action rejected")
    return "observed"


def _default_restore(
    step: str, restore: str, manifest: dict[str, Any], approval: dict[str, Any]
) -> None:
    if restore == "none" or restore == "retain-provider-resources":
        return
    if step == "control-host-loss":
        _hetzner_action(manifest, "poweron")
        return
    timeout = min(approval["deadline_seconds"], 300)
    if step == "agent-wal":
        _remote(
            manifest,
            "control-plane",
            _start_units_program(("nginx.service",)),
            timeout,
        )
    elif step == "staleness":
        raw = _remote(
            manifest,
            "canary",
            _stale_producer_program("restore"),
            timeout,
        )
        if json.loads(raw) not in (
            {"schema_version": 1, "state": "absent"},
            {"schema_version": 1, "state": "restored"},
        ):
            raise AcceptanceError("stale producer restoration rejected")
        _remote(
            manifest,
            "canary",
            _start_units_program(("observability-agent.service",)),
            timeout,
        )
    elif step == "grouping-inhibition":
        _remote(
            manifest,
            "control-plane",
            _matrix_resolve_program(manifest["hosts"]["canary"]),
            timeout,
        )
    elif step == "finite-silence":
        raw = _remote(
            manifest,
            "control-plane",
            _finite_silence_restore_program(
                _silence_owner(manifest),
                manifest["hosts"]["canary"],
                _silence_binding(approval),
            ),
            timeout,
        )
        if json.loads(raw) != {"schema_version": 1, "state": "restored"}:
            raise AcceptanceError("finite silence restoration rejected")
    elif step == "primary-lifecycle":
        _remote(manifest, "control-plane", _critical_resolve_program(), timeout)
    elif step == "deadman-lifecycle":
        _remote(
            manifest,
            "control-plane",
            _start_units_program(("observability-deadman-pulse.timer",)),
            timeout,
        )
    elif step == "control-service-loss":
        _remote(
            manifest,
            "control-plane",
            _start_units_program(
                (
                    "observability-prometheus.service",
                    "observability-alertmanager.service",
                    "observability-deadman-pulse.timer",
                )
            ),
            timeout,
        )
    elif step == "deadman-service-loss":
        _remote(
            manifest,
            "deadman",
            _start_units_program(("observability-deadman.service",)),
            timeout,
        )
    elif step == "primary-authority-loss":
        _operator(manifest, "rotate", "control-plane", confirm=True)
        _remote(manifest, "control-plane", _primary_canary_program(True), timeout)
    elif step == "invalid-candidate-refusal":
        expected = _rollback_generation(manifest)
        state = _generation_state(
            _remote(manifest, "control-plane", _control_plane_generation_program(), 30)
        )
        if state["current"] != expected:
            _operator(
                manifest,
                "rollback",
                "control-plane",
                confirm=True,
                variables=manifest["inputs"]["control_plane_vars"],
                secrets=manifest["inputs"]["control_plane_secrets"],
            )
    elif step == "valid-candidate-activation":
        _operator(
            manifest,
            "rollback",
            "control-plane",
            confirm=True,
            variables=manifest["inputs"]["control_plane_vars"],
            secrets=manifest["inputs"]["control_plane_secrets"],
        )


def _receipt_dir(path: Path) -> Path:
    absolute = path.absolute()
    _safe_parent(absolute / "placeholder")
    try:
        metadata = absolute.stat(follow_symlinks=False)
    except OSError:
        raise AcceptanceError("private receipt directory required") from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise AcceptanceError("private receipt directory required")
    return absolute


def _receipt_path(root: Path, step: str) -> Path:
    return root / f"{STEPS.index(step) + 1:02d}-{step}.json"


def _existing_receipt(
    root: Path, step: str, manifest: dict[str, Any]
) -> dict[str, Any] | None:
    path = _receipt_path(root, step)
    if not path.exists():
        return None
    value, _ = _private_json(path, "receipt conflict")
    try:
        started = _parse_time(value["started_at"])
        completed = _parse_time(value["completed_at"])
        if (
            set(value)
            != {
                "schema_version",
                "action",
                "result",
                "started_at",
                "completed_at",
                "source_revision",
                "deployable_digest",
            }
            or value["schema_version"] != 1
            or value["action"] != step
            or value["result"] != "observed"
            or value["source_revision"] != manifest["source_revision"]
            or value["deployable_digest"] != manifest["deployable_digest"]
            or completed < started
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise AcceptanceError("receipt conflict") from None
    return value


def _record_completion(
    journal: dict[str, Any], step: str, observations: dict[str, bool]
) -> None:
    completed = set(journal["completed_checks"])
    if step in ACCEPTANCE_CHECKS:
        journal["completed_checks"] = [
            name for name in ACCEPTANCE_CHECKS if name in completed | {step}
        ]
    else:
        journal["components_removed"] = True
    journal["human_observations"] = observations
    journal["current_step"] = None
    if (
        journal["components_removed"]
        and journal["completed_checks"] == list(ACCEPTANCE_CHECKS)
        and all(journal["human_observations"].values())
    ):
        journal["status"] = "ready-for-cleanup"
        journal["completed_checks"] = sorted(ACCEPTANCE_CHECKS)
        journal.pop("manifest_sha256", None)
        journal.pop("current_step", None)


def advance(
    manifest_path: Path,
    journal_path: Path,
    receipt_directory: Path,
    *,
    executor: Callable[[str, dict[str, Any], dict[str, Any]], str] | None = None,
    restorer: Callable[[str, str, dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    _debug_disabled()
    manifest, digest = load_manifest(manifest_path)
    receipt_root = _receipt_dir(receipt_directory)
    _safe_parent(journal_path.absolute())
    if executor is None:
        _source_identity(manifest)
        executor = _default_execute
    if restorer is None:
        restorer = _default_restore
    lock_path = receipt_root / ".acceptance.lock"
    lock_fd = os.open(
        lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = _utc_now()
        journal = _journal(journal_path, manifest, digest)
        if journal["status"] == "ready-for-cleanup":
            return {
                "schema_version": 1,
                "status": "ready-for-cleanup",
                "completed_step": None,
            }
        if journal["current_step"] is not None:
            step = journal["current_step"]["name"]
            receipt = _existing_receipt(receipt_root, step, manifest)
            if receipt is not None:
                _record_completion(
                    journal,
                    step,
                    _observations(
                        manifest,
                        step=step,
                        started_at=journal["current_step"]["started_at"],
                        receipt_sha256=hashlib.sha256(_canonical(receipt)).hexdigest(),
                        completed_at=receipt["completed_at"],
                    ),
                )
                _atomic_private(journal_path, journal)
                return {
                    "schema_version": 1,
                    "status": journal["status"],
                    "completed_step": step,
                }
            approval = _approval(manifest, step, now)
            restorer(step, STEP_RESTORES[step], manifest, approval)
            journal["current_step"] = None
            journal["status"] = "incomplete"
            _atomic_private(journal_path, journal)
            raise AcceptanceError("interrupted step restored; review required")
        completed = set(journal["completed_checks"])
        if journal["components_removed"]:
            completed.add("component-removal")
        step = next(
            (candidate for candidate in STEPS if candidate not in completed), None
        )
        if step is None:
            raise AcceptanceError("journal rejected")
        approval = _approval(manifest, step, now)
        journal["status"] = "active"
        journal["current_step"] = {"name": step, "started_at": _timestamp(now)}
        _atomic_private(journal_path, journal)
        try:
            result = executor(step, manifest, approval)
            if result != "observed":
                raise AcceptanceError("action result rejected")
        except Exception as exc:
            restore_failed = False
            try:
                restorer(step, STEP_RESTORES[step], manifest, approval)
            except Exception:
                restore_failed = True
            finally:
                journal["current_step"] = None
                journal["status"] = "incomplete"
                _atomic_private(journal_path, journal)
            if restore_failed:
                raise AcceptanceError("bounded restore failed") from None
            if isinstance(exc, AcceptanceError):
                raise
            raise AcceptanceError("bounded action failed") from None
        completed_at = _utc_now()
        receipt = {
            "schema_version": 1,
            "action": step,
            "result": "observed",
            "started_at": _timestamp(now),
            "completed_at": _timestamp(completed_at),
            "source_revision": manifest["source_revision"],
            "deployable_digest": manifest["deployable_digest"],
        }
        receipt_path = _receipt_path(receipt_root, step)
        prior = _existing_receipt(receipt_root, step, manifest)
        if prior is not None and prior != receipt:
            raise AcceptanceError("receipt conflict")
        if prior is None:
            _atomic_private(receipt_path, receipt)
        try:
            observations = _observations(
                manifest,
                step=step,
                started_at=journal["current_step"]["started_at"],
                receipt_sha256=hashlib.sha256(_canonical(receipt)).hexdigest(),
                completed_at=receipt["completed_at"],
            )
        except AcceptanceError:
            # Keep the completed machine row and its receipt current. The next
            # invocation can bind a later owner observation without repeating
            # the fault or losing the fixed restoration evidence.
            _atomic_private(journal_path, journal)
            raise
        _record_completion(journal, step, observations)
        _atomic_private(journal_path, journal)
        return {
            "schema_version": 1,
            "status": journal["status"],
            "completed_step": step,
        }
    except BlockingIOError:
        raise AcceptanceError("acceptance controller already active") from None
    finally:
        os.close(lock_fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="observability-staging-acceptance.py")
    commands = parser.add_subparsers(dest="command", required=True)
    advance_parser = commands.add_parser("advance")
    advance_parser.add_argument("--manifest", type=Path, required=True)
    advance_parser.add_argument("--journal", type=Path, required=True)
    advance_parser.add_argument("--receipts", type=Path, required=True)
    advance_parser.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if not args.confirm:
            raise AcceptanceError("--confirm required")
        result = advance(args.manifest, args.journal, args.receipts)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except AcceptanceError as exc:
        print(f"observability-staging-acceptance: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
