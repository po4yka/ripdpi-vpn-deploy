#!/usr/bin/env python3
"""Fail-closed receiver for the independent observability dead-man pulse.

The program deliberately has no fleet, provider, Prometheus, or primary-bot
credentials.  It accepts one compact HMAC-authenticated control-plane pulse,
persists only bounded delivery state, and makes secondary notifications through
its separately supplied systemd credential.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import threading
import time
from typing import Any
from urllib import request

import fcntl

MAX_STATE_BYTES = 4096
GENERATION = re.compile(r"^[0-9a-f]{40,64}$")
SIGNATURE = re.compile(r"^[0-9a-f]{64}$")


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
        "telegram",
    }
    if set(data) != required or data.get("schema") != 1:
        raise DeadmanError("invalid config")
    if data["pulse_path"] != "/v1/pulse" or data["pulse_interval_seconds"] != 60:
        raise DeadmanError("invalid config")
    if (
        data["missed_pulse_limit"] != 5
        or not isinstance(data["max_future_seconds"], int)
        or not 1 <= data["max_future_seconds"] <= 60
    ):
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
    if not isinstance(data["reverse_health_url"], str) or not data[
        "reverse_health_url"
    ].startswith("https://"):
        raise DeadmanError("invalid config")
    if data["reverse_health_max_bytes"] not in range(256, 4097):
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
    if not isinstance(data, dict):
        raise DeadmanError("unsafe state")
    if set(data) == oldest_fields or set(data) == prior_fields:
        data = {**_empty_state(), **data}
    if set(data) != current_fields:
        raise DeadmanError("unsafe state")
    if (
        data["schema"] != 1
        or not all(
            isinstance(data[key], int) and data[key] >= 0
            for key in (
                "last_sequence",
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
    for _ in range(config["retry_attempts"]):
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
        except (OSError, ValueError):
            continue
    return False


def _reverse_health(
    config: dict[str, Any], token: bytes, state: dict[str, Any], now: int
) -> bool:
    """Publish the only reverse summary this role owns; no raw diagnostics leave it."""
    payload: dict[str, Any] = {
        "schema": 1,
        "issued_at": datetime.fromtimestamp(now, UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "sequence": state["last_sequence"],
        "health": {
            "receiver": "incident" if state["incident"] else "healthy",
            "delivery": state["last_delivery"],
        },
    }
    payload["signature"] = hmac.new(
        token, _canonical(payload), hashlib.sha256
    ).hexdigest()
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(body) > config["reverse_health_max_bytes"]:
        raise DeadmanError("invalid reverse health")
    for _ in range(config["retry_attempts"]):
        try:
            with request.urlopen(
                request.Request(
                    config["reverse_health_url"],
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                ),
                timeout=config["retry_timeout_seconds"],
            ) as response:
                if response.status == 204:
                    return True
        except (OSError, ValueError):
            continue
    return False


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
    token = _read_token(Path(os.environ["CREDENTIALS_DIRECTORY"]) / "pulse-token")
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

    status_server = BoundedPulseServer((status_host, int(status_port)), StatusHandler)
    threading.Thread(target=status_server.serve_forever, daemon=True).start()
    BoundedPulseServer((host, int(port)), Handler).serve_forever()
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
