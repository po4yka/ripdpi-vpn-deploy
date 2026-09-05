#!/usr/bin/env python3
"""Bounded control-plane half of the independent dead-man pipeline."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import sys
import threading
import time
from typing import Any, Callable
from urllib import error, request

MAX_JSON_BYTES = 4096
MAX_CANARY_BYTES = 65536
GENERATION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SIGNATURE = re.compile(r"[0-9a-f]{64}\Z")
CANARY_FIELDS = {"schema", "kind", "generation", "observed_at"}
PRIMARY_FIELDS = {
    "schema",
    "kind",
    "generation",
    "attempted_at",
    "successful_at",
    "status",
}
REVERSE_AXES = {
    "receiver",
    "delivery",
    "cpu",
    "memory",
    "disk",
    "inode",
    "clock",
    "network",
    "unit",
    "collector",
    "source",
}
REVERSE_STATES = {
    "ok",
    "error",
    "healthy",
    "incident",
    "never",
    "firing",
    "recovery",
    "failed",
}
STATE_FIELDS = {
    "generation.json": {"schema", "generation"},
    "canary.json": CANARY_FIELDS,
    "primary-canary.json": PRIMARY_FIELDS,
    "pulse-state.json": {"schema", "generation", "last_sequence", "last_attempt"},
    "reverse-state.json": {
        "schema",
        "generation",
        "last_sequence",
        "last_received",
    },
}


class PipelineError(RuntimeError):
    """A categorical error safe to expose without request content."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PipelineError("invalid json")
        value[key] = item
    return value


def _decode(raw: bytes, maximum: int, category: str) -> dict[str, Any]:
    if not raw or len(raw) > maximum:
        raise PipelineError(category)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, PipelineError) as exc:
        raise PipelineError(category) from exc
    if not isinstance(value, dict):
        raise PipelineError(category)
    return value


def _canonical(payload: dict[str, Any]) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("signature", None)
    return json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode()


def _instant(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace("+00:00", "Z")


def _parse_instant(value: object, now: int, future: int) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PipelineError("invalid reverse")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PipelineError("invalid reverse") from exc
    stamp = int(parsed.timestamp())
    if parsed.tzinfo != UTC or stamp < 0 or stamp > now + future:
        raise PipelineError("invalid reverse")
    return stamp


def _open_trusted_directory(path: Path, *, allow_final_sticky: bool = False) -> int:
    if not path.is_absolute() or path == Path("/"):
        raise PipelineError("unsafe directory")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        components = path.parts[1:]
        for index, component in enumerate(components):
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
            metadata = os.fstat(descriptor)
            mode = stat.S_IMODE(metadata.st_mode)
            shared_textfile = (
                allow_final_sticky
                and index == len(components) - 1
                and mode == 0o3775
                and metadata.st_uid in {0, os.geteuid()}
            )
            if metadata.st_uid not in {0, os.geteuid()} or (
                mode & 0o022 and not shared_textfile
            ):
                raise PipelineError("unsafe directory")
        return descriptor
    except (OSError, PipelineError) as exc:
        os.close(descriptor)
        raise PipelineError("unsafe directory") from exc


def _ensure_private_directory(path: Path) -> None:
    try:
        parent = _open_trusted_directory(path.parent)
        try:
            try:
                os.mkdir(path.name, mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
            descriptor = os.open(
                path.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
        finally:
            os.close(parent)
        try:
            metadata = os.fstat(descriptor)
            if (
                metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise PipelineError("unsafe directory")
        finally:
            os.close(descriptor)
    except (OSError, PipelineError) as exc:
        raise PipelineError("unsafe directory") from exc


def _atomic_bytes(
    path: Path,
    content: bytes,
    mode: int = 0o600,
    *,
    allow_sticky_parent: bool = False,
) -> None:
    parent = _open_trusted_directory(
        path.parent, allow_final_sticky=allow_sticky_parent
    )
    temporary = f".pipeline-{os.getpid()}-{secrets.token_hex(8)}"
    descriptor = -1
    try:
        try:
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and (
            not stat.S_ISREG(current.st_mode)
            or current.st_uid != os.geteuid()
            or stat.S_IMODE(current.st_mode) != mode
        ):
            raise PipelineError("unsafe state")
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            mode,
            dir_fd=parent,
        )
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise PipelineError("state write failed")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            # Atomic replacement consumes the temporary pathname.
            pass
        os.close(parent)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    content = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    if len(content) > MAX_JSON_BYTES:
        raise PipelineError("state too large")
    _atomic_bytes(path, content)


def _read_private_json(path: Path, fields: set[str]) -> dict[str, Any]:
    try:
        parent = _open_trusted_directory(path.parent)
        try:
            metadata = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            descriptor = os.open(
                path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
        finally:
            os.close(parent)
        try:
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
                or metadata.st_size > MAX_JSON_BYTES
            ):
                raise PipelineError("unsafe state")
            content = os.read(descriptor, MAX_JSON_BYTES + 1)
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise PipelineError("unsafe state")
        finally:
            os.close(descriptor)
    except (OSError, PipelineError) as exc:
        raise PipelineError("unsafe state") from exc
    value = _decode(content, MAX_JSON_BYTES, "unsafe state")
    if set(value) != fields:
        raise PipelineError("unsafe state")
    return value


def _unlink_private_file(path: Path) -> None:
    parent = _open_trusted_directory(path.parent)
    descriptor = -1
    try:
        metadata = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            raise PipelineError("unsafe state")
        os.unlink(path.name, dir_fd=parent)
        os.fsync(parent)
    except (OSError, PipelineError) as exc:
        raise PipelineError("unsafe state") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _valid_state_document(name: str, value: dict[str, Any]) -> bool:
    state_generation = value.get("generation")
    if (
        value.get("schema") != 1
        or not isinstance(state_generation, str)
        or GENERATION.fullmatch(state_generation) is None
    ):
        return False
    if name == "canary.json":
        return (
            value.get("kind") == "alertmanager-watchdog"
            and isinstance(value.get("observed_at"), int)
            and not isinstance(value.get("observed_at"), bool)
        )
    if name == "primary-canary.json":
        return (
            value.get("kind") == "primary-telegram-canary"
            and value.get("status") in {"success", "failed"}
            and all(
                isinstance(value.get(field), int)
                and not isinstance(value.get(field), bool)
                for field in ("attempted_at", "successful_at")
            )
        )
    return all(
        isinstance(value.get(field), int)
        and not isinstance(value.get(field), bool)
        and value[field] >= 0
        for field in STATE_FIELDS[name] - {"schema", "generation"}
    )


def reconcile_state(state_dir: Path, generation: str, *, disable: bool = False) -> bool:
    if GENERATION.fullmatch(generation) is None or not isinstance(disable, bool):
        raise PipelineError("unsafe state")
    with _lock(state_dir):
        parent = _open_trusted_directory(state_dir)
        try:
            names = set(os.listdir(parent))
        except OSError as exc:
            raise PipelineError("unsafe state") from exc
        finally:
            os.close(parent)
        if names - (set(STATE_FIELDS) | {".pipeline.lock"}):
            raise PipelineError("unsafe state")
        documents: dict[str, dict[str, Any]] = {}
        for name, fields in STATE_FIELDS.items():
            if name not in names:
                continue
            document = _read_private_json(state_dir / name, fields)
            if not _valid_state_document(name, document):
                raise PipelineError("unsafe state")
            documents[name] = document
        observed = {value["generation"] for value in documents.values()}
        if len(observed) > 1:
            raise PipelineError("unsafe state")
        if disable:
            for name in sorted(documents):
                _unlink_private_file(state_dir / name)
            return bool(documents)
        marker = documents.get("generation.json")
        if documents and marker is None:
            raise PipelineError("unsafe state")
        if marker is not None and observed == {generation}:
            return False
        for name in sorted(documents):
            _unlink_private_file(state_dir / name)
        _atomic_json(
            state_dir / "generation.json", {"schema": 1, "generation": generation}
        )
        return True


@contextmanager
def _lock(state_dir: Path):  # type: ignore[no-untyped-def]
    _ensure_private_directory(state_dir)
    parent = _open_trusted_directory(state_dir)
    descriptor = os.open(
        ".pipeline.lock",
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=parent,
    )
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise PipelineError("unsafe state")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)
        os.close(parent)


def _require_generation_locked(state_dir: Path, generation: str) -> None:
    marker = _read_private_json(
        state_dir / "generation.json", STATE_FIELDS["generation.json"]
    )
    observed = marker.get("generation")
    if (
        marker.get("schema") != 1
        or not isinstance(observed, str)
        or observed != generation
        or GENERATION.fullmatch(observed) is None
    ):
        raise PipelineError("generation mismatch")


def record_canary(path: Path, raw: bytes, generation: str, now: int) -> dict[str, Any]:
    if (
        GENERATION.fullmatch(generation) is None
        or not isinstance(now, int)
        or isinstance(now, bool)
        or now < 0
    ):
        raise PipelineError("invalid canary")
    payload = _decode(raw, MAX_CANARY_BYTES, "invalid canary")
    expected = {
        "version",
        "groupKey",
        "truncatedAlerts",
        "status",
        "receiver",
        "groupLabels",
        "commonLabels",
        "commonAnnotations",
        "externalURL",
        "alerts",
    }
    labels = payload.get("commonLabels")
    annotations = payload.get("commonAnnotations")
    alerts = payload.get("alerts")
    alert = alerts[0] if isinstance(alerts, list) and len(alerts) == 1 else None
    alert_fields = {
        "status",
        "labels",
        "annotations",
        "startsAt",
        "endsAt",
        "generatorURL",
        "fingerprint",
    }
    if (
        set(payload) != expected
        or payload.get("version") != "4"
        or payload.get("status") != "firing"
        or payload.get("receiver") != "deadman-canary"
        or payload.get("truncatedAlerts") != 0
        or not isinstance(payload.get("groupKey"), str)
        or not 1 <= len(payload["groupKey"]) <= 512
        or payload.get("groupLabels") != {"alertname": "ObservabilityPipelineWatchdog"}
        or not isinstance(labels, dict)
        or set(labels) != {"alertname", "component", "severity"}
        or labels
        != {
            "alertname": "ObservabilityPipelineWatchdog",
            "component": "observability-pipeline",
            "severity": "watchdog",
        }
        or annotations != {"source_generation": generation}
        or not isinstance(payload.get("externalURL"), str)
        or len(payload["externalURL"]) > 512
        or not isinstance(alert, dict)
        or set(alert) != alert_fields
        or alert.get("status") != "firing"
        or alert.get("labels") != labels
        or alert.get("annotations") != {"source_generation": generation}
        or alert.get("endsAt") != "0001-01-01T00:00:00Z"
        or alert.get("generatorURL") != ""
        or not isinstance(alert.get("fingerprint"), str)
        or re.fullmatch(r"[0-9a-f]{16,64}", alert["fingerprint"]) is None
    ):
        raise PipelineError("invalid canary")
    try:
        started = _parse_instant(alert["startsAt"], now, 30)
    except PipelineError as exc:
        raise PipelineError("invalid canary") from exc
    if started > now:
        raise PipelineError("invalid canary")
    receipt = {
        "schema": 1,
        "kind": "alertmanager-watchdog",
        "generation": generation,
        "observed_at": now,
    }
    with _lock(path.parent):
        _require_generation_locked(path.parent, generation)
        _atomic_json(path, receipt)
    return receipt


def _canary_authorized(headers: Any, token: bytes) -> bool:
    values = headers.get_all("Authorization", [])
    if len(values) != 1 or not isinstance(values[0], str):
        return False
    supplied = values[0]
    if not supplied.startswith("Bearer "):
        return False
    try:
        expected = "Bearer " + token.decode("ascii")
    except UnicodeDecodeError:
        return False
    return hmac.compare_digest(supplied, expected)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _pulse_tls_context(ca_pem: bytes) -> ssl.SSLContext:
    if not ca_pem or len(ca_pem) > MAX_CANARY_BYTES or b"\x00" in ca_pem:
        raise PipelineError("pulse CA unavailable")
    try:
        decoded = ca_pem.decode("ascii")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_verify_locations(cadata=decoded)
    except (UnicodeDecodeError, ssl.SSLError, ValueError) as exc:
        raise PipelineError("pulse CA unavailable") from exc
    return context


def _post(
    url: str, body: bytes, timeout: int, context: ssl.SSLContext | None = None
) -> int:
    if context is None:
        raise PipelineError("pulse CA unavailable")
    outbound = request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener = request.build_opener(
        request.ProxyHandler({}), request.HTTPSHandler(context=context), _NoRedirect()
    )
    for attempt in range(2):
        try:
            with opener.open(outbound, timeout=timeout) as response:
                body = response.read(MAX_JSON_BYTES + 1)
                if len(body) > MAX_JSON_BYTES:
                    raise PipelineError("pulse response too large")
                return response.status
        except error.HTTPError as exc:
            if exc.code in {301, 302, 307, 308}:
                raise PipelineError("pulse redirect refused") from exc
            return exc.code
        except (error.URLError, TimeoutError, OSError) as exc:
            if attempt == 1:
                raise PipelineError("pulse transport failed") from exc
            time.sleep(0.1)
    raise PipelineError("pulse transport failed")


def _primary_canary_payload(generation: str, now: int) -> bytes:
    labels = {
        "alertname": "ObservabilityPrimaryTelegramCanary",
        "environment": "control",
        "node": "observability-control-plane",
        "component": "observability-pipeline",
    }
    annotations = {
        "source_generation": generation,
        "summary": "Primary Telegram route canary.",
        "evidence_class": "synthetic-primary-canary",
        "runbook": "docs/RUNBOOK-incident.md",
    }
    return json.dumps(
        {
            "version": "4",
            "groupKey": "primary-telegram-canary",
            "truncatedAlerts": 0,
            "status": "firing",
            "receiver": "telegram-canary",
            "groupLabels": {"alertname": labels["alertname"]},
            "commonLabels": labels,
            "commonAnnotations": {"source_generation": generation},
            "externalURL": "",
            "alerts": [
                {
                    "status": "firing",
                    "labels": labels,
                    "annotations": annotations,
                    "startsAt": _instant(now),
                    "endsAt": "0001-01-01T00:00:00Z",
                    "generatorURL": "",
                    "fingerprint": hashlib.sha256(
                        (generation + ":primary-canary").encode()
                    ).hexdigest()[:16],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def send_primary_canary(
    *,
    state_dir: Path,
    generation: str,
    relay_url: str,
    relay_token: bytes,
    now: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    if (
        GENERATION.fullmatch(generation) is None
        or relay_url != "http://127.0.0.1:19095/alert"
        or len(relay_token) != 64
        or not 1 <= timeout_seconds <= 5
    ):
        raise PipelineError("invalid primary canary contract")
    outbound = request.Request(
        relay_url,
        data=_primary_canary_payload(generation, now),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + relay_token.decode("ascii"),
        },
    )
    success = False
    opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(outbound, timeout=timeout_seconds) as response:
            success = (
                response.status == 200
                and len(response.read(MAX_JSON_BYTES + 1)) <= MAX_JSON_BYTES
            )
    except (error.HTTPError, error.URLError, TimeoutError, OSError):
        success = False
    receipt = {
        "schema": 1,
        "kind": "primary-telegram-canary",
        "generation": generation,
        "attempted_at": now,
        "successful_at": now if success else 0,
        "status": "success" if success else "failed",
    }
    with _lock(state_dir):
        _require_generation_locked(state_dir, generation)
        _atomic_json(state_dir / "primary-canary.json", receipt)
    if not success:
        raise PipelineError("primary canary failed")
    return receipt


def _ready(url: str, timeout_seconds: int) -> bool:
    if url not in {"http://127.0.0.1:9090/-/ready", "http://127.0.0.1:19094/-/ready"}:
        raise PipelineError("invalid readiness url")
    try:
        with request.urlopen(url, timeout=timeout_seconds) as response:
            return (
                response.status == 200
                and len(response.read(MAX_JSON_BYTES + 1)) <= MAX_JSON_BYTES
            )
    except OSError:
        return False


def publish_pulse(
    *,
    state_dir: Path,
    primary_status: dict[str, Any],
    token: bytes,
    generation: str,
    deadman_url: str,
    now: int,
    freshness_seconds: int,
    primary_freshness_seconds: int,
    timeout_seconds: int,
    tls_context: ssl.SSLContext,
    sender: Callable[..., int] = _post,
) -> dict[str, Any]:
    if (
        GENERATION.fullmatch(generation) is None
        or not deadman_url.startswith("https://")
        or not 60 <= freshness_seconds <= 900
        or not 3600 <= primary_freshness_seconds <= 172800
        or not 1 <= timeout_seconds <= 5
        or not 20 <= len(token) <= 128
        or not isinstance(tls_context, ssl.SSLContext)
    ):
        raise PipelineError("invalid pulse contract")
    state_path = state_dir / "pulse-state.json"
    with _lock(state_dir):
        _require_generation_locked(state_dir, generation)
        canary = _read_private_json(state_dir / "canary.json", CANARY_FIELDS)
        if (
            set(primary_status) != PRIMARY_FIELDS
            or canary["schema"] != 1
            or canary["kind"] != "alertmanager-watchdog"
            or canary["generation"] != generation
            or not isinstance(canary["observed_at"], int)
            or not 0 <= now - canary["observed_at"] <= freshness_seconds
            or primary_status["schema"] != 1
            or primary_status["kind"] != "primary-telegram-canary"
            or primary_status["generation"] != generation
            or primary_status["status"] != "success"
            or not isinstance(primary_status["successful_at"], int)
            or not 0
            <= now - primary_status["successful_at"]
            <= primary_freshness_seconds
        ):
            raise PipelineError("pipeline unhealthy")
        sequence = 1
        if state_path.exists():
            state = _read_private_json(
                state_path, {"schema", "generation", "last_sequence", "last_attempt"}
            )
            if (
                state["schema"] != 1
                or state["generation"] != generation
                or not isinstance(state["last_sequence"], int)
                or state["last_sequence"] < 0
            ):
                raise PipelineError("unsafe state")
            sequence = state["last_sequence"] + 1
        if sequence > 2**63 - 1:
            raise PipelineError("sequence exhausted")
        durable = {
            "schema": 1,
            "generation": generation,
            "last_sequence": sequence,
            "last_attempt": now,
        }
        _atomic_json(state_path, durable)
    pulse: dict[str, Any] = {
        "schema": 1,
        "generation": generation,
        "sequence": sequence,
        "issued_at": _instant(now),
        "expires_at": _instant(now + 30),
        "health": {
            "prometheus": True,
            "alertmanager": True,
            "canary": True,
            "primary_telegram": True,
        },
    }
    pulse["signature"] = hmac.new(token, _canonical(pulse), hashlib.sha256).hexdigest()
    body = json.dumps(pulse, separators=(",", ":")).encode()
    if sender(deadman_url, body, timeout_seconds, tls_context) != 204:
        raise PipelineError("pulse rejected")
    return pulse


def _reverse_metrics(payload: dict[str, Any], now: int) -> bytes:
    lines = [
        "# HELP vpn_observability_deadman_reverse_fresh Last reverse heartbeat freshness.",
        "# TYPE vpn_observability_deadman_reverse_fresh gauge",
        'vpn_observability_deadman_reverse_fresh{generation="'
        + payload["generation"]
        + '",state="fresh"} 1',
        'vpn_observability_deadman_reverse_fresh{generation="'
        + payload["generation"]
        + '",state="stale"} 0',
        "# HELP vpn_observability_deadman_health Bounded reverse health state.",
        "# TYPE vpn_observability_deadman_health gauge",
    ]
    for axis in sorted(REVERSE_AXES):
        for state in sorted(REVERSE_STATES):
            value = 1 if payload["health"][axis] == state else 0
            lines.append(
                "vpn_observability_deadman_health{"
                f'check="{axis}",generation="{payload["generation"]}",state="{state}"'
                f"}} {value}"
            )
    lines.extend(
        [
            "# HELP vpn_observability_deadman_reverse_timestamp_seconds Last accepted reverse heartbeat.",
            "# TYPE vpn_observability_deadman_reverse_timestamp_seconds gauge",
            'vpn_observability_deadman_reverse_timestamp_seconds{generation="'
            + payload["generation"]
            + f'"}} {now}',
        ]
    )
    return ("\n".join(lines) + "\n").encode()


def accept_reverse(
    *,
    state_dir: Path,
    metrics_path: Path,
    raw: bytes,
    token: bytes,
    generation: str,
    now: int,
    max_future_seconds: int,
) -> dict[str, Any]:
    payload = _decode(raw, MAX_JSON_BYTES, "invalid reverse")
    if (
        set(payload)
        != {
            "schema",
            "generation",
            "sequence",
            "issued_at",
            "health",
            "signature",
        }
        or payload.get("schema") != 1
        or payload.get("generation") != generation
        or not isinstance(payload.get("sequence"), int)
        or not 1 <= payload["sequence"] <= 2**63 - 1
        or not isinstance(payload.get("health"), dict)
        or set(payload["health"]) != REVERSE_AXES
        or any(value not in REVERSE_STATES for value in payload["health"].values())
        or not isinstance(payload.get("signature"), str)
        or SIGNATURE.fullmatch(payload["signature"]) is None
    ):
        raise PipelineError("invalid reverse")
    issued = _parse_instant(payload["issued_at"], now, max_future_seconds)
    if now - issued > 180:
        raise PipelineError("invalid reverse")
    expected = hmac.new(token, _canonical(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload["signature"]):
        raise PipelineError("invalid reverse")
    state_path = state_dir / "reverse-state.json"
    with _lock(state_dir):
        _require_generation_locked(state_dir, generation)
        if state_path.exists():
            prior = _read_private_json(
                state_path,
                {"schema", "generation", "last_sequence", "last_received"},
            )
            if (
                prior["schema"] != 1
                or prior["generation"] != generation
                or not isinstance(prior["last_sequence"], int)
                or payload["sequence"] <= prior["last_sequence"]
            ):
                raise PipelineError("invalid reverse")
        state = {
            "schema": 1,
            "generation": generation,
            "last_sequence": payload["sequence"],
            "last_received": now,
        }
        _atomic_json(state_path, state)
        _atomic_bytes(
            metrics_path,
            _reverse_metrics(payload, now),
            mode=0o644,
            allow_sticky_parent=True,
        )
    return state


class PipelineServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4


def _read_body(handler: BaseHTTPRequestHandler, maximum: int) -> bytes:
    raw_length = handler.headers.get("Content-Length", "")
    if re.fullmatch(r"[0-9]{1,6}", raw_length) is None:
        raise PipelineError("invalid body")
    length = int(raw_length)
    if not 0 < length <= maximum:
        raise PipelineError("invalid body")
    body = handler.rfile.read(length)
    if len(body) != length:
        raise PipelineError("invalid body")
    return body


def _serve(args: argparse.Namespace, token: bytes, canary_token: bytes) -> int:
    state_dir = Path(args.state_dir)
    reconcile_state(state_dir, args.generation)
    canary_host, canary_port = args.canary_listen.rsplit(":", 1)
    reverse_host, reverse_port = args.reverse_listen.rsplit(":", 1)

    class CanaryHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            try:
                if self.path != "/alerts" or not _canary_authorized(
                    self.headers, canary_token
                ):
                    raise PipelineError("invalid canary")
                record_canary(
                    state_dir / "canary.json",
                    _read_body(self, MAX_CANARY_BYTES),
                    args.generation,
                    int(time.time()),
                )
            except PipelineError:
                self.send_error(400)
                return
            self.send_response(204)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    class ReverseHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            try:
                if self.path != "/v1/deadman/reverse":
                    raise PipelineError("invalid reverse")
                accept_reverse(
                    state_dir=state_dir,
                    metrics_path=Path(args.metrics_path),
                    raw=_read_body(self, MAX_JSON_BYTES),
                    token=token,
                    generation=args.generation,
                    now=int(time.time()),
                    max_future_seconds=30,
                )
            except PipelineError:
                self.send_error(400)
                return
            self.send_response(204)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    canary = PipelineServer((canary_host, int(canary_port)), CanaryHandler)
    reverse = PipelineServer((reverse_host, int(reverse_port)), ReverseHandler)
    thread = threading.Thread(target=canary.serve_forever, daemon=True)
    thread.start()
    try:
        reverse.serve_forever()
    finally:
        canary.shutdown()
        canary.server_close()
        thread.join(timeout=5)
        reverse.server_close()
    return 0


def _credential_bytes(name: str, maximum: int) -> bytes:
    directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if (
        not directory
        or "/" in name
        or name in {".", ".."}
        or not 1 <= maximum <= MAX_CANARY_BYTES
    ):
        raise PipelineError("credential unavailable")
    content = (Path(directory) / name).read_bytes()
    if not content or len(content) > maximum:
        raise PipelineError("credential unavailable")
    return content


def _credential(name: str) -> bytes:
    content = _credential_bytes(name, 128).strip()
    if not 20 <= len(content) <= 128 or any(chr(byte).isspace() for byte in content):
        raise PipelineError("credential unavailable")
    return content


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--canary-listen", required=True)
    serve.add_argument("--reverse-listen", required=True)
    serve.add_argument("--state-dir", required=True)
    serve.add_argument("--metrics-path", required=True)
    serve.add_argument("--generation", required=True)
    serve.add_argument("--pulse-credential", default="pulse-token")
    serve.add_argument("--canary-credential", default="canary-token")
    pulse = commands.add_parser("publish-pulse")
    pulse.add_argument("--state-dir", required=True)
    pulse.add_argument("--primary-status", required=True)
    pulse.add_argument("--deadman-url", required=True)
    pulse.add_argument("--generation", required=True)
    pulse.add_argument("--freshness-seconds", type=int, required=True)
    pulse.add_argument("--primary-freshness-seconds", type=int, required=True)
    pulse.add_argument("--timeout-seconds", type=int, required=True)
    pulse.add_argument("--pulse-credential", default="pulse-token")
    pulse.add_argument("--pulse-ca-credential", default="pulse-ca")
    pulse.add_argument("--prometheus-ready", required=True)
    pulse.add_argument("--alertmanager-ready", required=True)
    canary = commands.add_parser("primary-canary")
    canary.add_argument("--state-dir", required=True)
    canary.add_argument("--relay-url", required=True)
    canary.add_argument("--generation", required=True)
    canary.add_argument("--timeout-seconds", type=int, required=True)
    canary.add_argument("--relay-credential", default="relay-token")
    reconcile = commands.add_parser("reconcile-state")
    reconcile.add_argument("--state-dir", required=True)
    reconcile.add_argument("--generation", required=True)
    reconcile.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            token = _credential(args.pulse_credential)
            canary_token = _credential(args.canary_credential)
            return _serve(args, token, canary_token)
        if args.command == "reconcile-state":
            changed = reconcile_state(
                Path(args.state_dir), args.generation, disable=args.disable
            )
            print(json.dumps({"changed": changed}, separators=(",", ":")))
            return 0
        if args.command == "primary-canary":
            send_primary_canary(
                state_dir=Path(args.state_dir),
                generation=args.generation,
                relay_url=args.relay_url,
                relay_token=_credential(args.relay_credential),
                now=int(time.time()),
                timeout_seconds=args.timeout_seconds,
            )
            return 0
        token = _credential(args.pulse_credential)
        ca_pem = _credential_bytes(args.pulse_ca_credential, MAX_CANARY_BYTES)
        if not _ready(args.prometheus_ready, args.timeout_seconds) or not _ready(
            args.alertmanager_ready, args.timeout_seconds
        ):
            raise PipelineError("pipeline unhealthy")
        primary = _read_private_json(Path(args.primary_status), PRIMARY_FIELDS)
        publish_pulse(
            state_dir=Path(args.state_dir),
            primary_status=primary,
            token=token,
            generation=args.generation,
            deadman_url=args.deadman_url,
            now=int(time.time()),
            freshness_seconds=args.freshness_seconds,
            primary_freshness_seconds=args.primary_freshness_seconds,
            timeout_seconds=args.timeout_seconds,
            tls_context=_pulse_tls_context(ca_pem),
        )
        return 0
    except (OSError, PipelineError, UnicodeError):
        print("deadman-pipeline: refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
