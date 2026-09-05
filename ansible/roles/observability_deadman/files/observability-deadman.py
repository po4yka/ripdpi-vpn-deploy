#!/usr/bin/env python3
"""Fail-closed receiver for the independent observability dead-man pulse.

The program deliberately has no fleet, provider, Prometheus, or primary-bot
credentials.  It accepts one compact HMAC-authenticated control-plane pulse,
persists only bounded delivery state, and makes secondary notifications through
its separately supplied systemd credential.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib import error, request

import fcntl

# Keep the retry delay injectable without mutating the process-wide ``time``
# module.  The receiver itself always gets the standard implementation.
_sleep = time.sleep

MAX_STATE_BYTES = 4096
MAX_TELEGRAM_ERROR_BYTES = 1024
GENERATION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SIGNATURE = re.compile(r"^[0-9a-f]{64}$")
REVERSE_HEALTH_URL = re.compile(
    r"https://[A-Za-z0-9][A-Za-z0-9.-]{0,252}:9443/observability/v1/deadman/reverse"
)
CLIENT_CN = "deadman-control"
PULSE_SERVER_NAME = re.compile(
    r"(?:localhost|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:[.][a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?){1,4})"
)
HEALTH_AXES = {
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


class DeadmanError(RuntimeError):
    """A deliberately redacted, safe-to-log rejection."""


class BoundedPulseServer(ThreadingHTTPServer):
    """A small public ingestion listener; the private status server reuses it."""

    request_queue_size = 4
    daemon_threads = True


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeadmanError("invalid pulse")
        result[key] = value
    return result


def _instant(value: object, now: int, *, future: int) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DeadmanError("invalid pulse")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DeadmanError("invalid pulse") from exc
    if parsed.tzinfo != UTC:
        raise DeadmanError("invalid pulse")
    stamp = int(parsed.timestamp())
    if stamp < 0 or stamp > now + future:
        raise DeadmanError("invalid pulse")
    return stamp


def _canonical(payload: dict[str, Any]) -> bytes:
    clone = dict(payload)
    clone.pop("signature", None)
    return json.dumps(clone, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _read_token(path: Path) -> bytes:
    try:
        content = path.read_bytes().strip()
    except OSError as exc:
        raise DeadmanError("credential unavailable") from exc
    if not 20 <= len(content) <= 128 or any(chr(byte).isspace() for byte in content):
        raise DeadmanError("credential unavailable")
    return content


def _load_config(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DeadmanError("invalid config") from exc
    if len(raw) > MAX_STATE_BYTES:
        raise DeadmanError("invalid config")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, DeadmanError) as exc:
        raise DeadmanError("invalid config") from exc
    required = {
        "schema",
        "pulse_path",
        "pulse_interval_seconds",
        "missed_pulse_limit",
        "max_future_seconds",
        "max_pulse_bytes",
        "retry_attempts",
        "retry_timeout_seconds",
        "reminder_interval_seconds",
        "canary_interval_seconds",
        "reverse_health_url",
        "reverse_health_max_bytes",
        "source_generation",
        "required_units",
        "pulse_tls",
        "reverse_health_tls",
        "telegram",
    }
    if set(data) != required or data.get("schema") != 1:
        raise DeadmanError("invalid config")
    if data["pulse_path"] != "/v1/pulse" or data["pulse_interval_seconds"] != 60:
        raise DeadmanError("invalid config")
    if data["missed_pulse_limit"] != 5 or data["max_future_seconds"] != 30:
        raise DeadmanError("invalid config")
    if (
        not isinstance(data["max_pulse_bytes"], int)
        or not 512 <= data["max_pulse_bytes"] <= 4096
    ):
        raise DeadmanError("invalid config")
    if data["retry_attempts"] not in (1, 2) or data[
        "retry_timeout_seconds"
    ] not in range(1, 6):
        raise DeadmanError("invalid config")
    if (
        data["reminder_interval_seconds"] != 3600
        or data["canary_interval_seconds"] != 86400
    ):
        raise DeadmanError("invalid config")
    if not isinstance(
        data["reverse_health_url"], str
    ) or not REVERSE_HEALTH_URL.fullmatch(data["reverse_health_url"]):
        raise DeadmanError("invalid config")
    if data["reverse_health_max_bytes"] not in range(256, 4097):
        raise DeadmanError("invalid config")
    pulse_tls = data["pulse_tls"]
    if (
        not isinstance(pulse_tls, dict)
        or set(pulse_tls)
        != {"server_name", "server_cert_credential", "server_key_credential"}
        or not isinstance(pulse_tls["server_name"], str)
        or PULSE_SERVER_NAME.fullmatch(pulse_tls["server_name"]) is None
        or pulse_tls["server_cert_credential"] != "pulse-server-cert"
        or pulse_tls["server_key_credential"] != "pulse-server-key"
    ):
        raise DeadmanError("invalid config")
    if not isinstance(data["source_generation"], str) or not GENERATION.fullmatch(
        data["source_generation"]
    ):
        raise DeadmanError("invalid config")
    if (
        not isinstance(data["required_units"], list)
        or not 1 <= len(data["required_units"]) <= 8
        or len(set(data["required_units"])) != len(data["required_units"])
        or any(
            not isinstance(unit, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9@_.-]{0,63}[.]service", unit) is None
            for unit in data["required_units"]
        )
    ):
        raise DeadmanError("invalid config")
    tls = data["reverse_health_tls"]
    if (
        not isinstance(tls, dict)
        or set(tls)
        != {
            "ca_credential",
            "client_cert_credential",
            "client_key_credential",
            "client_cn",
            "client_cert_fingerprint_sha256",
            "ca_fingerprint_sha256",
        }
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value) is None
            for value in (
                tls["ca_credential"],
                tls["client_cert_credential"],
                tls["client_key_credential"],
            )
        )
        or tls["client_cn"] != CLIENT_CN
        or any(
            not isinstance(tls[name], str) or SIGNATURE.fullmatch(tls[name]) is None
            for name in (
                "client_cert_fingerprint_sha256",
                "ca_fingerprint_sha256",
            )
        )
        or tls["client_cert_fingerprint_sha256"] == tls["ca_fingerprint_sha256"]
    ):
        raise DeadmanError("invalid config")
    telegram = data["telegram"]
    if not isinstance(telegram, dict) or set(telegram) != {"chat_id", "topic_id"}:
        raise DeadmanError("invalid config")
    if not isinstance(telegram["chat_id"], str) or not re.fullmatch(
        r"-?[0-9]{6,20}", telegram["chat_id"]
    ):
        raise DeadmanError("invalid config")
    if not isinstance(telegram["topic_id"], int) or telegram["topic_id"] < 0:
        raise DeadmanError("invalid config")
    return data


def _empty_state() -> dict[str, Any]:
    return {
        "schema": 1,
        "last_sequence": 0,
        "last_reverse_sequence": 0,
        "last_expiry": 0,
        "last_pulse": 0,
        "incident": False,
        "last_delivery": "never",
        "last_delivery_at": 0,
        "last_canary": 0,
        "last_canary_delivery": "never",
        "pending_event": "none",
        "pending_nonce": 0,
        "pending_at": 0,
    }


def _state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_STATE_BYTES
        ):
            raise DeadmanError("unsafe state")
        data = json.loads(path.read_text("utf-8"), object_pairs_hook=_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, DeadmanError) as exc:
        raise DeadmanError("unsafe state") from exc
    oldest_fields = {
        "schema",
        "last_sequence",
        "last_expiry",
        "last_pulse",
        "incident",
        "last_delivery",
    }
    prior_fields = oldest_fields | {"last_delivery_at", "last_canary"}
    current_fields = set(_empty_state())
    legacy_current_fields = current_fields - {"last_reverse_sequence"}
    if not isinstance(data, dict):
        raise DeadmanError("unsafe state")
    observed_fields = frozenset(data)
    if observed_fields in {
        frozenset(oldest_fields),
        frozenset(prior_fields),
        frozenset(legacy_current_fields),
    }:
        data = {**_empty_state(), **data}
    if set(data) != current_fields:
        raise DeadmanError("unsafe state")
    if (
        data["schema"] != 1
        or not all(
            isinstance(data[key], int) and data[key] >= 0
            for key in (
                "last_sequence",
                "last_reverse_sequence",
                "last_expiry",
                "last_pulse",
                "last_delivery_at",
                "last_canary",
                "pending_nonce",
                "pending_at",
            )
        )
        or not isinstance(data["incident"], bool)
        or data["last_delivery"] not in {"never", "firing", "recovery", "failed"}
        or data["last_canary_delivery"] not in {"never", "success", "failed"}
        or data["pending_event"] not in {"none", "firing", "recovery", "canary"}
    ):
        raise DeadmanError("unsafe state")
    return data


_LOCK_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.Lock] = {}


@contextmanager
def _state_lock(path: Path):  # type: ignore[no-untyped-def]
    """Serialize HTTP workers and timer processes around one state RMW transaction."""
    key = str(path.resolve())
    with _LOCK_GUARD:
        local = _LOCAL_LOCKS.setdefault(key, threading.Lock())
    with local:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            path.parent / ".state.lock", os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600
        )
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        encoded = json.dumps(data, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        if len(encoded) > MAX_STATE_BYTES:
            raise DeadmanError("unsafe state")
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise DeadmanError("unsafe state")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            # A successful atomic replacement consumes the temporary pathname.
            pass


def accept_pulse(
    raw: bytes, token: bytes, state: dict[str, Any], config: dict[str, Any], now: int
) -> dict[str, Any]:
    if len(raw) > config["max_pulse_bytes"]:
        raise DeadmanError("invalid pulse")
    try:
        pulse = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, DeadmanError) as exc:
        raise DeadmanError("invalid pulse") from exc
    expected = {
        "schema",
        "generation",
        "sequence",
        "issued_at",
        "expires_at",
        "health",
        "signature",
    }
    if not isinstance(pulse, dict) or set(pulse) != expected or pulse["schema"] != 1:
        raise DeadmanError("invalid pulse")
    if not isinstance(pulse["generation"], str) or not GENERATION.fullmatch(
        pulse["generation"]
    ):
        raise DeadmanError("invalid pulse")
    if (
        not isinstance(pulse["sequence"], int)
        or pulse["sequence"] <= state["last_sequence"]
        or pulse["sequence"] > 2**63 - 1
    ):
        raise DeadmanError("invalid pulse")
    issued = _instant(pulse["issued_at"], now, future=config["max_future_seconds"])
    expiry = _instant(pulse["expires_at"], now, future=config["max_future_seconds"])
    if issued > expiry or expiry <= now or expiry <= state["last_expiry"]:
        raise DeadmanError("invalid pulse")
    health = pulse["health"]
    if (
        not isinstance(health, dict)
        or set(health) != {"prometheus", "alertmanager", "canary", "primary_telegram"}
        or not all(isinstance(value, bool) for value in health.values())
    ):
        raise DeadmanError("invalid pulse")
    signature = pulse["signature"]
    if not isinstance(signature, str) or not SIGNATURE.fullmatch(signature):
        raise DeadmanError("invalid pulse")
    actual = hmac.new(token, _canonical(pulse), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(actual, signature):
        raise DeadmanError("invalid pulse")
    if not all(health.values()):
        raise DeadmanError("unhealthy pulse")
    state.update(last_sequence=pulse["sequence"], last_expiry=expiry, last_pulse=now)
    return state


def accept_and_save(
    path: Path, raw: bytes, token: bytes, config: dict[str, Any], now: int
) -> dict[str, Any]:
    with _state_lock(path):
        accepted = accept_pulse(raw, token, _state(path), config, now)
        _save_state(path, accepted)
        return accepted


def _read_pulse_body(stream: Any, length: int, maximum: int) -> bytes:
    if length < 0 or length > maximum:
        raise DeadmanError("invalid pulse")
    try:
        body = stream.read(length)
    except OSError as exc:
        raise DeadmanError("invalid pulse") from exc
    if len(body) != length:
        raise DeadmanError("invalid pulse")
    return body


def _telegram_retry_after(body: bytes) -> int | None:
    """Read only Telegram's bounded flood-control field from an error body."""
    if not body or len(body) > MAX_TELEGRAM_ERROR_BYTES:
        return None
    try:
        payload = json.loads(body.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, DeadmanError):
        return None
    if not isinstance(payload, dict) or set(payload) - {
        "ok",
        "error_code",
        "description",
        "parameters",
    }:
        return None
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        return None
    retry_after = parameters.get("retry_after")
    if isinstance(retry_after, bool) or not isinstance(retry_after, int):
        return None
    return retry_after if 0 <= retry_after <= 999_999 else None


def _telegram_retry_delay(headers: Any, body: bytes, attempt: int, maximum: int) -> int:
    """Return a bounded retry delay without retaining response content."""
    retry_after = headers.get("Retry-After") if headers is not None else None
    if isinstance(retry_after, str) and re.fullmatch(r"[0-9]{1,6}", retry_after):
        return min(int(retry_after), maximum)
    body_delay = _telegram_retry_after(body)
    if body_delay is not None:
        return min(body_delay, maximum)
    return min(1 << attempt, maximum)


def _telegram(config: dict[str, Any], credential: bytes, event: str) -> bool:
    """Send a bounded, deliberately non-sensitive secondary message."""
    if event not in {"firing", "recovery", "canary"}:
        raise DeadmanError("invalid event")
    payload: dict[str, Any] = {
        "chat_id": config["telegram"]["chat_id"],
        "text": "[secondary dead-man] monitoring-plane " + event,
        "disable_web_page_preview": True,
    }
    if config["telegram"]["topic_id"]:
        payload["message_thread_id"] = config["telegram"]["topic_id"]
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    # The credential stays in the HTTPS path but is never included in an error.
    endpoint = (
        "https://api.telegram.org/bot" + credential.decode("ascii") + "/sendMessage"
    )
    attempts = config["retry_attempts"]
    for attempt in range(attempts):
        retry_headers = None
        retry_body = b""
        try:
            with request.urlopen(
                request.Request(
                    endpoint,
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                ),
                timeout=config["retry_timeout_seconds"],
            ) as response:
                if response.status == 200:
                    return True
                if response.status != 429 and not 500 <= response.status <= 599:
                    return False
                retry_headers = getattr(response, "headers", None)
                if response.status == 429:
                    try:
                        retry_body = response.read(MAX_TELEGRAM_ERROR_BYTES + 1)
                    except (AttributeError, OSError, ValueError):
                        retry_body = b""
        except error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code <= 599:
                return False
            retry_headers = exc.headers
            if exc.code == 429:
                try:
                    retry_body = exc.read(MAX_TELEGRAM_ERROR_BYTES + 1)
                except (AttributeError, OSError, ValueError):
                    retry_body = b""
        except (OSError, ValueError):
            # A transport failure has no trustworthy response metadata.
            retry_headers = None
            retry_body = b""
        if attempt + 1 < attempts:
            delay = _telegram_retry_delay(
                retry_headers,
                retry_body,
                attempt,
                config["retry_timeout_seconds"],
            )
            if delay:
                _sleep(delay)
    return False


def _host_health(
    config: dict[str, Any], state: dict[str, Any], now: int
) -> dict[str, str]:
    """Collect only one bounded categorical result for each owned health axis."""
    health = {axis: "error" for axis in HEALTH_AXES}
    try:
        health["cpu"] = (
            "ok" if all(value >= 0 for value in os.getloadavg()) else "error"
        )
    except OSError:
        health["cpu"] = "error"
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        health["memory"] = "ok" if pages > 0 and page_size > 0 else "error"
    except (OSError, ValueError):
        health["memory"] = "error"
    try:
        filesystem = os.statvfs(
            str(config.get("state_dir", "/var/lib/observability-deadman"))
        )
        health["disk"] = "ok" if filesystem.f_bavail >= 0 else "error"
        health["inode"] = "ok" if filesystem.f_favail >= 0 else "error"
    except OSError:
        health["disk"] = "error"
        health["inode"] = "error"
    health["clock"] = "ok" if abs(int(time.time()) - now) <= 5 else "error"
    try:
        interfaces = Path("/sys/class/net")
        health["network"] = (
            "ok"
            if any(
                entry.name != "lo"
                and (entry / "operstate").read_text("ascii").strip() == "up"
                for entry in interfaces.iterdir()
            )
            else "error"
        )
    except (OSError, UnicodeError):
        health["network"] = "error"
    try:
        units = subprocess.run(
            ["systemctl", "is-active", "--quiet", *config["required_units"]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        health["unit"] = "ok" if units.returncode == 0 else "error"
    except (OSError, subprocess.TimeoutExpired):
        health["unit"] = "error"
    health["collector"] = "ok" if state.get("schema") == 1 else "error"
    health["source"] = (
        "ok"
        if GENERATION.fullmatch(str(config.get("source_generation", "")))
        else "error"
    )
    return health


def _reverse_context(config: dict[str, Any]) -> ssl.SSLContext:
    credentials = Path(os.environ["CREDENTIALS_DIRECTORY"])
    tls = config["reverse_health_tls"]
    context = ssl.create_default_context(cafile=str(credentials / tls["ca_credential"]))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        certfile=str(credentials / tls["client_cert_credential"]),
        keyfile=str(credentials / tls["client_key_credential"]),
    )
    return context


def _pulse_context(config: dict[str, Any]) -> ssl.SSLContext:
    credentials = Path(os.environ.get("CREDENTIALS_DIRECTORY", ""))
    tls = config["pulse_tls"]
    if not credentials.is_dir():
        raise DeadmanError("credential unavailable")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(
            certfile=str(credentials / tls["server_cert_credential"]),
            keyfile=str(credentials / tls["server_key_credential"]),
        )
    except (OSError, ssl.SSLError) as exc:
        raise DeadmanError("credential unavailable") from exc
    return context


class _RejectRedirects(request.HTTPRedirectHandler):
    """Keep reverse health bound to its configured origin and route."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _reverse_opener(context: ssl.SSLContext | None) -> request.OpenerDirector:
    handlers: list[request.BaseHandler] = [
        request.ProxyHandler({}),
        _RejectRedirects(),
    ]
    if context is not None:
        handlers.append(request.HTTPSHandler(context=context))
    return request.build_opener(*handlers)


def _post_reverse(
    config: dict[str, Any],
    _token: bytes,
    payload: dict[str, Any],
    context: ssl.SSLContext | None,
) -> bool:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(body) > config["reverse_health_max_bytes"]:
        raise DeadmanError("invalid reverse health")
    opener = _reverse_opener(context)
    for _ in range(config["retry_attempts"]):
        try:
            outbound = request.Request(
                config["reverse_health_url"],
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with opener.open(
                outbound, timeout=config["retry_timeout_seconds"]
            ) as response:
                if response.status == 204:
                    return True
        except error.HTTPError as exc:
            if exc.code in {301, 302, 307, 308}:
                return False
        except (OSError, ValueError):
            continue
    return False


def _reverse_health(
    config: dict[str, Any], token: bytes, state: dict[str, Any], now: int
) -> bool:
    """Publish the only reverse summary this role owns; no raw diagnostics leave it."""
    host_health = _host_health(config, state, now)
    payload: dict[str, Any] = {
        "schema": 1,
        "generation": str(config.get("source_generation", "a" * 40)),
        "issued_at": datetime.fromtimestamp(now, UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "sequence": state["last_reverse_sequence"],
        "health": {
            "receiver": "incident" if state["incident"] else "healthy",
            "delivery": state["last_delivery"],
            **host_health,
        },
    }
    payload["signature"] = hmac.new(
        token, _canonical(payload), hashlib.sha256
    ).hexdigest()
    context = None
    if "reverse_health_tls" in config and os.environ.get("CREDENTIALS_DIRECTORY"):
        try:
            context = _reverse_context(config)
        except (OSError, ssl.SSLError, KeyError) as exc:
            raise DeadmanError("invalid reverse health") from exc
    return _post_reverse(config, token, payload, context)


def _reserve_delivery(
    path: Path,
    config: dict[str, Any],
    now: int,
) -> tuple[dict[str, Any], tuple[str, int] | None]:
    with _state_lock(path):
        state = _state(path)
        if (
            state["pending_event"] != "none"
            and now - state["pending_at"]
            >= config["retry_attempts"] * config["retry_timeout_seconds"] + 1
        ):
            if state["pending_event"] == "canary":
                state["last_canary_delivery"] = "failed"
                state["last_canary"] = state["pending_at"]
            else:
                state["last_delivery"] = "failed"
                state["last_delivery_at"] = state["pending_at"]
            state["pending_event"] = "none"
            state["pending_at"] = 0
            _save_state(path, state)
        if state["pending_event"] != "none":
            return dict(state), None
        overdue = (
            state["last_pulse"] == 0
            or now - state["last_pulse"]
            >= config["pulse_interval_seconds"] * config["missed_pulse_limit"]
        )
        event: str | None = None
        notification_due = (
            now - state["last_delivery_at"] >= config["reminder_interval_seconds"]
        )
        if overdue and (not state["incident"] or notification_due):
            state["incident"] = True
            event = "firing"
        elif not overdue and state["incident"]:
            state["incident"] = False
            event = "recovery"
        if (
            not state["incident"]
            and event is None
            and (
                now - state["last_canary"] >= config["canary_interval_seconds"]
                or (
                    state["last_canary_delivery"] == "failed"
                    and now - state["last_canary"]
                    >= config["reminder_interval_seconds"]
                )
            )
        ):
            event = "canary"
        if event is not None:
            state["pending_nonce"] += 1
            state["pending_event"] = event
            state["pending_at"] = now
            _save_state(path, state)
            return dict(state), (event, state["pending_nonce"])
        return dict(state), None


def _complete_delivery(
    path: Path, event: str, nonce: int, success: bool, now: int
) -> dict[str, Any]:
    with _state_lock(path):
        state = _state(path)
        if state["pending_event"] != event or state["pending_nonce"] != nonce:
            return state
        state["pending_event"] = "none"
        state["pending_at"] = 0
        if event == "canary":
            state["last_canary_delivery"] = "success" if success else "failed"
            state["last_canary"] = now
        else:
            state["last_delivery"] = event if success else "failed"
            state["last_delivery_at"] = now
        _save_state(path, state)
        return state


def _reserve_reverse_sequence(path: Path) -> dict[str, Any]:
    with _state_lock(path):
        state = _state(path)
        if state["last_reverse_sequence"] >= 2**63 - 1:
            raise DeadmanError("reverse sequence exhausted")
        state["last_reverse_sequence"] += 1
        _save_state(path, state)
        return state


def tick(
    path: Path,
    config: dict[str, Any],
    telegram_token: bytes,
    pulse_token: bytes,
    now: int,
) -> dict[str, Any]:
    state, reservation = _reserve_delivery(path, config, now)
    if reservation is not None:
        event, nonce = reservation
        state = _complete_delivery(
            path, event, nonce, _telegram(config, telegram_token, event), now
        )
    state = _reserve_reverse_sequence(path)
    _reverse_health(config, pulse_token, state, now)
    return state


def _status_payload(state: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            "schema": 1,
            "incident": state["incident"],
            "last_delivery": state["last_delivery"],
            "last_pulse": state["last_pulse"],
            "last_canary_delivery": state["last_canary_delivery"],
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _serve(arguments: argparse.Namespace) -> int:
    config = _load_config(Path(arguments.config))
    credentials = Path(os.environ.get("CREDENTIALS_DIRECTORY", ""))
    token = _read_token(credentials / "pulse-token")
    state_path = Path(arguments.state)
    host, port = arguments.listen.rsplit(":", 1)
    status_host, status_port = arguments.status_listen.rsplit(":", 1)
    requests = threading.BoundedSemaphore(4)

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != config["pulse_path"]:
                self.send_error(404)
                return
            if not requests.acquire(blocking=False):
                self.send_error(503)
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                accept_and_save(
                    state_path,
                    _read_pulse_body(self.rfile, length, config["max_pulse_bytes"]),
                    token,
                    config,
                    int(time.time()),
                )
            except (DeadmanError, OSError, ValueError):
                self.send_error(400)
                return
            finally:
                requests.release()
            self.send_response(204)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    class StatusHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/v1/status":
                self.send_error(404)
                return
            try:
                current = _state(state_path)
            except DeadmanError:
                self.send_error(503)
                return
            body = _status_payload(current)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    status_started = False

    class PulseServer(BoundedPulseServer):
        def service_actions(self) -> None:
            nonlocal status_started
            if not status_started:
                threading.Thread(
                    target=status_server.serve_forever, daemon=True
                ).start()
                status_started = True
            super().service_actions()

    with ExitStack() as startup:
        status_server = BoundedPulseServer(
            (status_host, int(status_port)), StatusHandler
        )
        startup.callback(status_server.server_close)
        pulse_server = PulseServer((host, int(port)), Handler)
        startup.callback(pulse_server.server_close)
        pulse_server.socket = _pulse_context(config).wrap_socket(
            pulse_server.socket, server_side=True
        )
        pulse_server.serve_forever()
    return 0


def _tick(arguments: argparse.Namespace) -> int:
    config = _load_config(Path(arguments.config))
    credentials = Path(os.environ["CREDENTIALS_DIRECTORY"])
    tick(
        Path(arguments.state),
        config,
        _read_token(credentials / "telegram-bot-token"),
        _read_token(credentials / "pulse-token"),
        int(time.time()),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-config")
    validate.add_argument("--config", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--config", required=True)
    serve.add_argument("--state", required=True)
    serve.add_argument("--listen", required=True)
    serve.add_argument("--status-listen", required=True)
    timer = commands.add_parser("tick")
    timer.add_argument("--config", required=True)
    timer.add_argument("--state", required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "validate-config":
            _load_config(Path(arguments.config))
            return 0
        return _serve(arguments) if arguments.command == "serve" else _tick(arguments)
    except DeadmanError as exc:
        print(str(exc), file=sys.stderr)
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
