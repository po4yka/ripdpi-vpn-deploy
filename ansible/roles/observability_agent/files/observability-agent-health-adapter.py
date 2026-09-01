#!/usr/bin/env python3
"""Adapt producer-owned watchdog and backup state into bounded metrics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time

MAX_WATCHDOG_BYTES = 4096
MAX_JSON_BYTES = 16 * 1024
MAX_COUNTER = 10_000_000_000
FUTURE_TOLERANCE_SECONDS = 30
NODE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
WATCHDOG_KEYS = {
    "consecutive_fails",
    "last_alert_epoch",
    "alerts_this_hour",
    "alerts_hour_started",
    "kicks_this_hour",
    "kicks_hour_started",
}
STAGES = ("local_backup", "integrity", "remote_copy")
STAGE_ROLES = {
    "local_backup": "local-backup",
    "integrity": "integrity",
    "remote_copy": "remote-copy",
}


class HealthAdapterError(RuntimeError):
    """A redacted producer-evidence error."""


@dataclass(frozen=True)
class SecureInput:
    content: bytes
    modified_at: int


@dataclass(frozen=True)
class WatchdogEvidence:
    values: dict[str, int]
    observed_at: int
    fresh: bool


@dataclass(frozen=True)
class BackupStageEvidence:
    payload: dict[str, object]
    observed_at: int
    fresh: bool


@dataclass(frozen=True)
class RestoreEvidence:
    payload: dict[str, object]
    verified_at: int
    snapshot_at: int
    fresh: bool


def _metric_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _sample(name: str, value: int, **labels: str) -> str:
    rendered = ""
    if labels:
        rendered = (
            "{"
            + ",".join(f'{key}="{_metric_label(item)}"' for key, item in labels.items())
            + "}"
        )
    return f"{name}{rendered} {value}"


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise HealthAdapterError("invalid evidence")
        payload[key] = value
    return payload


def _trusted_directory_fd(path: Path, *, shared_final: bool, error: str) -> int:
    if not path.is_absolute():
        raise HealthAdapterError(error)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    accepted_owners = {0, os.geteuid()}
    descriptor = os.open("/", flags)
    try:
        components = path.parts[1:]
        for index, component in enumerate(components):
            metadata = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            shared = (
                shared_final
                and index == len(components) - 1
                and bool(metadata.st_mode & stat.S_IWGRP)
                and bool(metadata.st_mode & stat.S_ISGID)
                and bool(metadata.st_mode & stat.S_ISVTX)
                and metadata.st_gid in {os.getegid(), *os.getgroups()}
            )
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid not in accepted_owners
                or bool(metadata.st_mode & stat.S_IWOTH)
                or (bool(metadata.st_mode & stat.S_IWGRP) and not shared)
            ):
                raise HealthAdapterError(error)
            child = os.open(component, flags, dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise HealthAdapterError(error)
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _require_directory_identity(descriptor: int, path: Path, error: str) -> None:
    observed = os.lstat(path)
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino)
    ):
        raise HealthAdapterError(error)


def _secure_read(path: Path, maximum: int, expected_modes: set[int]) -> SecureInput:
    try:
        parent_fd = _trusted_directory_fd(
            path.parent, shared_final=False, error="unsafe evidence"
        )
    except OSError as exc:
        raise HealthAdapterError("invalid evidence") from exc
    descriptor = -1
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) not in expected_modes
            or metadata.st_size > maximum
        ):
            raise HealthAdapterError("unsafe evidence")
        content = bytearray()
        while len(content) <= maximum:
            chunk = os.read(descriptor, min(4096, maximum + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > maximum:
            raise HealthAdapterError("unsafe evidence")
        _require_directory_identity(parent_fd, path.parent, "unsafe evidence")
        return SecureInput(bytes(content), int(metadata.st_mtime))
    except OSError as exc:
        raise HealthAdapterError("invalid evidence") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _parse_json(source: SecureInput) -> dict[str, object]:
    try:
        payload = json.loads(
            source.content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HealthAdapterError("invalid evidence") from exc
    if not isinstance(payload, dict):
        raise HealthAdapterError("invalid evidence")
    return payload


def _parse_timestamp(value: object, now: int) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise HealthAdapterError("invalid evidence")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise HealthAdapterError("invalid evidence") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise HealthAdapterError("invalid evidence")
    epoch = int(parsed.timestamp())
    if epoch < 0 or epoch > now + FUTURE_TOLERANCE_SECONDS:
        raise HealthAdapterError("invalid evidence")
    return epoch


def _parse_watchdog(path: Path, maximum_age: int, now: int) -> WatchdogEvidence:
    source = _secure_read(path, MAX_WATCHDOG_BYTES, {0o640})
    try:
        text = source.content.decode("ascii")
    except UnicodeDecodeError as exc:
        raise HealthAdapterError("invalid evidence") from exc
    values: dict[str, int] = {}
    for line in text.splitlines():
        if not line or line.count("=") != 1:
            raise HealthAdapterError("invalid evidence")
        key, raw = line.split("=", 1)
        if (
            key in values
            or key not in WATCHDOG_KEYS
            or not raw.isascii()
            or not raw.isdecimal()
        ):
            raise HealthAdapterError("invalid evidence")
        value = int(raw)
        if value > MAX_COUNTER:
            raise HealthAdapterError("invalid evidence")
        values[key] = value
    if set(values) != WATCHDOG_KEYS:
        raise HealthAdapterError("invalid evidence")
    for key in ("last_alert_epoch", "alerts_hour_started", "kicks_hour_started"):
        if values[key] > now + FUTURE_TOLERANCE_SECONDS:
            raise HealthAdapterError("invalid evidence")
    if source.modified_at > now + FUTURE_TOLERANCE_SECONDS:
        raise HealthAdapterError("invalid evidence")
    return WatchdogEvidence(
        values=values,
        observed_at=source.modified_at,
        fresh=now - source.modified_at <= maximum_age,
    )


def _validate_stage(stage: object, now: int, updated_at: int) -> dict[str, object]:
    if not isinstance(stage, dict) or set(stage) - {
        "result",
        "attempted_at",
        "succeeded_at",
        "failed_at",
    }:
        raise HealthAdapterError("invalid evidence")
    result = stage.get("result")
    if result not in {"pending", "success", "failed", "disabled"}:
        raise HealthAdapterError("invalid evidence")
    timestamps: dict[str, int] = {}
    for key in ("attempted_at", "succeeded_at", "failed_at"):
        if key in stage:
            timestamp = _parse_timestamp(stage[key], now)
            if timestamp > updated_at:
                raise HealthAdapterError("invalid evidence")
            timestamps[key] = timestamp
    keys = set(timestamps)
    if result == "success" and keys != {"attempted_at", "succeeded_at"}:
        raise HealthAdapterError("invalid evidence")
    if result == "failed" and keys != {"attempted_at", "failed_at"}:
        raise HealthAdapterError("invalid evidence")
    if result == "disabled" and keys:
        raise HealthAdapterError("invalid evidence")
    if result == "pending" and keys not in (set(), {"attempted_at"}):
        raise HealthAdapterError("invalid evidence")
    if "attempted_at" in timestamps:
        terminal = timestamps.get("succeeded_at", timestamps.get("failed_at"))
        if terminal is not None and terminal < timestamps["attempted_at"]:
            raise HealthAdapterError("invalid evidence")
    return {"result": result, **timestamps}


def _parse_backup_stage(path: Path, maximum_age: int, now: int) -> BackupStageEvidence:
    source = _secure_read(path, MAX_JSON_BYTES, {0o600})
    payload = _parse_json(source)
    if (
        set(payload) != {"version", "updated_at", *STAGES}
        or payload.get("version") != 1
    ):
        raise HealthAdapterError("invalid evidence")
    updated_at = _parse_timestamp(payload["updated_at"], now)
    normalized: dict[str, object] = {"version": 1, "updated_at": updated_at}
    for stage in STAGES:
        normalized[stage] = _validate_stage(payload[stage], now, updated_at)
    return BackupStageEvidence(
        payload=normalized,
        observed_at=updated_at,
        fresh=now - updated_at <= maximum_age,
    )


def _parse_restore(
    path: Path, maximum_age: int, snapshot_maximum_age: int, now: int
) -> RestoreEvidence:
    source = _secure_read(path, MAX_JSON_BYTES, {0o600})
    payload = _parse_json(source)
    if (
        set(payload)
        != {
            "version",
            "repository_source",
            "snapshot_id",
            "snapshot_time",
            "verified_at",
        }
        or payload.get("version") != 1
    ):
        raise HealthAdapterError("invalid evidence")
    repository_source = payload["repository_source"]
    snapshot_id = payload["snapshot_id"]
    if repository_source not in {"local", "remote"}:
        raise HealthAdapterError("invalid evidence")
    if not isinstance(snapshot_id, str) or not SHA256.fullmatch(snapshot_id):
        raise HealthAdapterError("invalid evidence")
    snapshot_at = _parse_timestamp(payload["snapshot_time"], now)
    verified_at = _parse_timestamp(payload["verified_at"], now)
    if snapshot_at > verified_at:
        raise HealthAdapterError("invalid evidence")
    fresh = (
        now - verified_at <= maximum_age
        and now - snapshot_at <= maximum_age + snapshot_maximum_age
    )
    return RestoreEvidence(payload, verified_at, snapshot_at, fresh)


def _freshness(node: str, role: str, fresh: bool) -> str:
    return _sample(
        "vpn_backup_freshness_state",
        1,
        node=node,
        role=role,
        state="fresh" if fresh else "stale",
    )


def _render_watchdog(node: str, evidence: WatchdogEvidence | None) -> list[str]:
    labels = {"node": node, "role": "watchdog"}
    if evidence is None:
        return [_sample("vpn_watchdog_collection_success", 0, **labels)]
    result = [
        _sample("vpn_watchdog_collection_success", int(evidence.fresh), **labels),
        _sample(
            "vpn_watchdog_last_run_timestamp_seconds", evidence.observed_at, **labels
        ),
        _sample(
            "vpn_watchdog_freshness_state",
            1,
            **labels,
            state="fresh" if evidence.fresh else "stale",
        ),
    ]
    if not evidence.fresh:
        return result
    values = evidence.values
    outcome = "not-attempted"
    if values["kicks_this_hour"]:
        outcome = "recovered" if values["consecutive_fails"] == 0 else "unresolved"
    result.extend(
        [
            _sample(
                "vpn_watchdog_result",
                1,
                **labels,
                state="healthy" if values["consecutive_fails"] == 0 else "failed",
            ),
            _sample(
                "vpn_watchdog_consecutive_failures",
                values["consecutive_fails"],
                **labels,
            ),
            _sample(
                "vpn_watchdog_restart_attempts", values["kicks_this_hour"], **labels
            ),
            _sample(
                "vpn_watchdog_rate_limit_state",
                1,
                node=node,
                role="alerts-rate-limit",
                state=(
                    "limited"
                    if values["alerts_this_hour"] >= _LIMITS["alerts"]
                    else "open"
                ),
            ),
            _sample(
                "vpn_watchdog_rate_limit_state",
                1,
                node=node,
                role="restart-rate-limit",
                state=(
                    "limited"
                    if values["kicks_this_hour"] >= _LIMITS["restarts"]
                    else "open"
                ),
            ),
            _sample("vpn_watchdog_recovery_outcome", 1, **labels, state=outcome),
        ]
    )
    return result


def _render_backup_stage(node: str, evidence: BackupStageEvidence | None) -> list[str]:
    labels = {"node": node, "role": "stage-status"}
    if evidence is None:
        return [_sample("vpn_backup_collection_success", 0, **labels)]
    result = [
        _sample("vpn_backup_collection_success", int(evidence.fresh), **labels),
        _sample(
            "vpn_backup_collected_timestamp_seconds", evidence.observed_at, **labels
        ),
        _freshness(node, "stage-status", evidence.fresh),
    ]
    if not evidence.fresh:
        return result
    for stage_name in STAGES:
        role = STAGE_ROLES[stage_name]
        stage = evidence.payload[stage_name]
        assert isinstance(stage, dict)
        result.append(
            _sample(
                "vpn_backup_result", 1, node=node, role=role, state=str(stage["result"])
            )
        )
        for field, family in (
            ("attempted_at", "vpn_backup_attempted_timestamp_seconds"),
            ("succeeded_at", "vpn_backup_succeeded_timestamp_seconds"),
            ("failed_at", "vpn_backup_failed_timestamp_seconds"),
        ):
            if field in stage:
                result.append(_sample(family, int(stage[field]), node=node, role=role))
    return result


def _render_restore(node: str, evidence: RestoreEvidence | None) -> list[str]:
    labels = {"node": node, "role": "restore-drill"}
    if evidence is None:
        return [_sample("vpn_backup_collection_success", 0, **labels)]
    result = [
        _sample("vpn_backup_collection_success", int(evidence.fresh), **labels),
        _sample(
            "vpn_backup_collected_timestamp_seconds", evidence.verified_at, **labels
        ),
        _freshness(node, "restore-drill", evidence.fresh),
        _sample(
            "vpn_backup_snapshot_timestamp_seconds", evidence.snapshot_at, **labels
        ),
    ]
    if evidence.fresh:
        result.append(
            _sample(
                "vpn_backup_restore_source",
                1,
                **labels,
                state=str(evidence.payload["repository_source"]),
            )
        )
    return result


def _validate_existing_output(parent_fd: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != os.getegid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o640
    ):
        raise HealthAdapterError("unsafe output")


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _atomic_write(path: Path, content: str) -> None:
    if path.name in {"", ".", ".."}:
        raise HealthAdapterError("unsafe output")
    parent_fd = _trusted_directory_fd(
        path.parent, shared_final=True, error="unsafe output"
    )
    temporary: str | None = None
    descriptor = -1
    try:
        _validate_existing_output(parent_fd, path.name)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        for _attempt in range(8):
            temporary = f".{path.name}.{secrets.token_hex(16)}.tmp"
            try:
                descriptor = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
                break
            except FileExistsError:
                temporary = None
        else:
            raise HealthAdapterError("unsafe output")
        _write_all(descriptor, content.encode("utf-8"))
        os.fchown(descriptor, os.geteuid(), os.getegid())
        os.fchmod(descriptor, 0o640)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _require_directory_identity(parent_fd, path.parent, "unsafe output")
        os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = None
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


_LIMITS = {"alerts": 0, "restarts": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--watchdog-state", type=Path, required=True)
    parser.add_argument("--watchdog-fail-threshold", type=int, required=True)
    parser.add_argument("--watchdog-alert-limit", type=int, required=True)
    parser.add_argument("--watchdog-restart-limit", type=int, required=True)
    parser.add_argument("--watchdog-max-age-seconds", type=int, required=True)
    parser.add_argument("--backup-stage", type=Path, required=True)
    parser.add_argument("--backup-stage-max-age-seconds", type=int, required=True)
    parser.add_argument("--restore-drill", type=Path, required=True)
    parser.add_argument("--restore-drill-max-age-seconds", type=int, required=True)
    parser.add_argument("--backup-snapshot-max-age-seconds", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (
        not NODE_ID.fullmatch(args.node_id)
        or not 1 <= args.watchdog_fail_threshold <= 100
        or not 1 <= args.watchdog_alert_limit <= 100
        or not 1 <= args.watchdog_restart_limit <= 100
        or not 60 <= args.watchdog_max_age_seconds <= 86400
        or not 3600 <= args.backup_stage_max_age_seconds <= 604800
        or not 86400 <= args.restore_drill_max_age_seconds <= 3888000
        or not 3600 <= args.backup_snapshot_max_age_seconds <= 604800
    ):
        print("observability-health-adapter: collection failed", file=sys.stderr)
        return 2
    _LIMITS["alerts"] = args.watchdog_alert_limit
    _LIMITS["restarts"] = args.watchdog_restart_limit
    now = int(time.time())
    failed = False
    try:
        watchdog = _parse_watchdog(
            args.watchdog_state, args.watchdog_max_age_seconds, now
        )
        failed |= not watchdog.fresh
    except HealthAdapterError:
        watchdog = None
        failed = True
    try:
        backup = _parse_backup_stage(
            args.backup_stage, args.backup_stage_max_age_seconds, now
        )
        failed |= not backup.fresh
    except HealthAdapterError:
        backup = None
        failed = True
    try:
        restore = _parse_restore(
            args.restore_drill,
            args.restore_drill_max_age_seconds,
            args.backup_snapshot_max_age_seconds,
            now,
        )
        failed |= not restore.fresh
    except HealthAdapterError:
        restore = None
        failed = True
    lines = [
        "# Managed by observability-agent-health-adapter.",
        *_render_watchdog(args.node_id, watchdog),
        *_render_backup_stage(args.node_id, backup),
        *_render_restore(args.node_id, restore),
        "",
    ]
    try:
        _atomic_write(args.output, "\n".join(lines))
    except (HealthAdapterError, OSError):
        failed = True
    if failed:
        print("observability-health-adapter: collection failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
