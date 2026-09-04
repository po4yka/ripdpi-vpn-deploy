#!/usr/bin/env python3
"""Private finite-silence authority; no Telegram or infrastructure actions."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
import re
import ssl
import time
from urllib.parse import urlsplit
from uuid import UUID

TOKEN = re.compile(r"[0-9a-f]{64}\Z")
ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
LABELS = {
    "alertname",
    "environment",
    "node",
    "component",
    "policy",
    "profile",
    "vantage",
    "severity",
}


class GatewayError(ValueError):
    """Only categorical errors may cross the HTTP boundary."""


def validate_silence(request, policy, now):
    if (
        not isinstance(request, dict)
        or set(request)
        != {"schema_version", "reason", "starts_at", "ends_at", "matchers"}
        or type(request["schema_version"]) is not int
        or request["schema_version"] != 1
    ):
        raise GatewayError("silence-shape")
    reason = request["reason"]
    if (
        not isinstance(reason, str)
        or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", reason)
        or len(reason) > 64
    ):
        raise GatewayError("silence-reason")
    matchers = request["matchers"]
    if (
        not isinstance(matchers, dict)
        or not 2 <= len(matchers) <= 8
        or set(matchers) - LABELS
        or matchers.get("environment") != policy["environment"]
        or not {"node", "policy"}.intersection(matchers)
        or any(
            not isinstance(value, str) or not ALIAS.fullmatch(value)
            for value in matchers.values()
        )
    ):
        raise GatewayError("silence-scope")
    try:
        start, end = [
            datetime.strptime(request[key], "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=UTC)
            .timestamp()
            for key in ("starts_at", "ends_at")
        ]
    except (TypeError, ValueError) as exc:
        raise GatewayError("silence-time") from exc
    if (
        not now - 60 <= start <= now + policy["max_ttl_seconds"]
        or not max(now, start) < end <= start + policy["max_ttl_seconds"]
    ):
        raise GatewayError("silence-ttl")
    return end


class AlertmanagerBackend:
    def __init__(self, url: str, context: ssl.SSLContext):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "127.0.0.1"
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or context.verify_mode != ssl.CERT_REQUIRED
            or not context.check_hostname
        ):
            raise GatewayError("backend-contract")
        self.port = parsed.port or 443
        self.context = context

    def request(self, method: str, path: str, body: bytes | None = None):
        connection = http.client.HTTPSConnection(
            "127.0.0.1", self.port, context=self.context, timeout=5
        )
        try:
            connection.request(
                method, path, body=body, headers={"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            payload = response.read(262145)
            if len(payload) > 262144 or not 200 <= response.status < 300:
                raise GatewayError("backend-refused")
            return payload
        except (OSError, http.client.HTTPException) as exc:
            raise GatewayError("backend-unavailable") from exc
        finally:
            connection.close()


class SilenceJournal:
    """One atomic, private bounded audit/state artifact; no request or token logs."""

    def __init__(self, directory, clock):
        self.path, self.clock = directory / "silences.json", clock
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise GatewayError("audit-directory")
        self.state = {"schema_version": 1, "silences": {}, "audit": []}
        if os.path.lexists(self.path):
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600
                ):
                    raise GatewayError("audit-file")
                payload = stream.read(1048577)
            if len(payload) > 1048576:
                raise GatewayError("audit-size")
            value = json.loads(payload)
            if (
                set(value) != set(self.state)
                or value["schema_version"] != 1
                or not isinstance(value["silences"], dict)
                or not isinstance(value["audit"], list)
                or len(value["silences"]) > 256
                or len(value["audit"]) > 1024
            ):
                raise GatewayError("audit-shape")
            for silence_id, row in value["silences"].items():
                if (
                    str(UUID(silence_id)) != silence_id
                    or set(row) != {"owner", "expires_at", "scope", "reason"}
                    or not ALIAS.fullmatch(row["owner"])
                    or type(row["expires_at"]) is not int
                ):
                    raise GatewayError("audit-entry")
            self.state = value

    def append(
        self, action, result, owner, *, silence_id=None, create=None, remove=False
    ):
        state = json.loads(json.dumps(self.state))
        event = {
            "at": int(self.clock()),
            "action": action,
            "result": result,
            "owner": owner,
        }
        if silence_id is not None:
            event["silence_id"] = silence_id
        if create is not None:
            if silence_id in state["silences"] or len(state["silences"]) >= 256:
                raise GatewayError("audit-capacity")
            state["silences"][silence_id] = create
            event.update(scope=create["scope"], reason=create["reason"])
        if remove:
            state["silences"].pop(silence_id)
        state["audit"] = (state["audit"] + [event])[-1024:]
        payload = (
            json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        if len(payload) > 1048576:
            raise GatewayError("audit-capacity")
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=".silence-", dir=self.path.parent
            )
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(
                self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.state = state
        except OSError as exc:
            raise GatewayError("audit-unavailable") from exc
        finally:
            if temporary and os.path.lexists(temporary):
                os.unlink(temporary)

    def expire(self):
        for silence_id, row in list(self.state["silences"].items()):
            if row["expires_at"] <= self.clock():
                self.append(
                    "expiry",
                    "elapsed",
                    row["owner"],
                    silence_id=silence_id,
                    remove=True,
                )


class GatewayServer(HTTPServer):
    def __init__(
        self,
        address,
        policy,
        authentication,
        backend,
        state_directory: Path,
        *,
        clock=time.time,
    ):
        if (
            not isinstance(policy, dict)
            or set(policy) != {"schema_version", "environment", "max_ttl_seconds"}
            or type(policy["schema_version"]) is not int
            or policy["schema_version"] != 1
            or not isinstance(policy["environment"], str)
            or not ALIAS.fullmatch(policy["environment"])
            or type(policy["max_ttl_seconds"]) is not int
            or not 60 <= policy["max_ttl_seconds"] <= 86400
        ):
            raise GatewayError("policy-contract")
        if (
            not isinstance(authentication, dict)
            or not isinstance(authentication.get("owners"), list)
            or any(not isinstance(row, dict) for row in authentication["owners"])
        ):
            raise GatewayError("authentication-contract")
        owners = authentication["owners"]
        digests = [row.get("token_sha256") for row in owners] + [
            authentication.get("sender_token_sha256")
        ]
        names = [row.get("owner") for row in owners]
        if (
            set(authentication) != {"schema_version", "owners", "sender_token_sha256"}
            or type(authentication["schema_version"]) is not int
            or authentication["schema_version"] != 1
            or not 1 <= len(owners) <= 32
            or any(set(row) != {"owner", "token_sha256"} for row in owners)
            or any(
                not isinstance(name, str)
                or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name)
                for name in names
            )
            or any(
                not isinstance(value, str) or not TOKEN.fullmatch(value)
                for value in digests
            )
            or len(set(digests)) != len(digests)
            or len(set(names)) != len(names)
        ):
            raise GatewayError("authentication-contract")
        if address[0] != "127.0.0.1":
            raise GatewayError("listen-contract")
        self.policy, self.authentication = policy, authentication
        self.backend, self.state_directory, self.clock = backend, state_directory, clock
        self.journal = SilenceJournal(state_directory, clock)
        self.journal.expire()
        super().__init__(address, GatewayHandler)

    def service_actions(self):
        self.journal.expire()

    def owner(self, authorization: str) -> str | None:
        if not authorization.startswith("Bearer ") or not TOKEN.fullmatch(
            authorization[7:]
        ):
            raise GatewayError("unauthenticated")
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        if hmac.compare_digest(digest, self.authentication["sender_token_sha256"]):
            return None
        for principal in self.authentication["owners"]:
            if hmac.compare_digest(digest, principal["token_sha256"]):
                return principal["owner"]
        raise GatewayError("unauthenticated")


class GatewayHandler(BaseHTTPRequestHandler):
    server: GatewayServer

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        pass

    def reply(self, status: int, payload):
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self, limit):
        sizes = self.headers.get_all("Content-Length", [])
        if (
            len(sizes) != 1
            or self.headers.get("Transfer-Encoding")
            or self.headers.get_content_type() != "application/json"
        ):
            raise GatewayError("request-framing")
        size = int(sizes[0])
        if not 1 <= size <= limit:
            raise GatewayError("request-size")
        body = self.rfile.read(size)
        if len(body) != size:
            raise GatewayError("request-size")
        return body

    def dispatch(self):
        owner = None
        action = (
            "create"
            if self.path == "/v1/silences"
            else "delete" if self.path.startswith("/v1/silences/") else "request"
        )
        try:
            if len(self.headers.get_all("Authorization", [])) != 1:
                raise GatewayError("unauthenticated")
            owner = self.server.owner(self.headers["Authorization"])
            route = (self.command, self.path)
            allowed = {
                ("GET", "/-/ready"),
                ("GET", "/metrics"),
                ("POST", "/api/v2/alerts"),
            }
            if owner is not None:
                allowed.add(("GET", "/api/v2/alerts"))
            if route in allowed:
                body = self.body(262144) if self.command == "POST" else None
                if body is not None and not isinstance(json.loads(body), list):
                    raise GatewayError("alerts-shape")
                if body is None and (
                    self.headers.get("Content-Length") not in (None, "0")
                    or self.headers.get("Transfer-Encoding")
                ):
                    raise GatewayError("request-framing")
                response = self.server.backend.request(self.command, self.path, body)
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.send_header(
                    "Content-Type",
                    "application/json" if "/api/" in self.path else "text/plain",
                )
                self.end_headers()
                self.wfile.write(response)
                return
            if (
                owner is not None
                and self.command == "DELETE"
                and self.path.startswith("/v1/silences/")
            ):
                silence_id = self.path.removeprefix("/v1/silences/")
                if (
                    str(UUID(silence_id)) != silence_id
                    or self.headers.get("Content-Length") not in (None, "0")
                    or self.headers.get("Transfer-Encoding")
                ):
                    raise GatewayError("delete-shape")
                self.server.journal.expire()
                row = self.server.journal.state["silences"].get(silence_id)
                if row is None or row["owner"] != owner:
                    self.server.journal.append("delete", "refused", owner)
                    self.reply(403, {"error": "delete-refused"})
                    return
                self.server.journal.append(
                    "delete", "attempt", owner, silence_id=silence_id
                )
                self.server.backend.request("DELETE", "/api/v2/silence/" + silence_id)
                self.server.journal.append(
                    "delete", "deleted", owner, silence_id=silence_id, remove=True
                )
                self.reply(200, {"silence_id": silence_id, "deleted": True})
                return
            if owner is None or route != ("POST", "/v1/silences"):
                self.server.journal.append(action, "route-refused", owner)
                self.reply(403, {"error": "route-refused"})
                return
            request = json.loads(self.body(8192), object_pairs_hook=unique_object)
            expiry = validate_silence(request, self.server.policy, self.server.clock())
            self.server.journal.expire()
            if len(self.server.journal.state["silences"]) >= 256:
                raise GatewayError("audit-capacity")
            self.server.journal.append("create", "attempt", owner)
            payload = {
                "createdBy": owner,
                "comment": request["reason"],
                "startsAt": request["starts_at"],
                "endsAt": request["ends_at"],
                "matchers": [
                    {"name": key, "value": value, "isRegex": False, "isEqual": True}
                    for key, value in sorted(request["matchers"].items())
                ],
            }
            result = json.loads(
                self.server.backend.request(
                    "POST", "/api/v2/silences", json.dumps(payload).encode()
                )
            )
            silence_id = str(UUID(result["silenceID"]))
            self.server.journal.append(
                "create",
                "created",
                owner,
                silence_id=silence_id,
                create={
                    "owner": owner,
                    "expires_at": int(expiry),
                    "scope": request["matchers"],
                    "reason": request["reason"],
                },
            )
            self.reply(201, {"silence_id": silence_id})
        except GatewayError as exc:
            try:
                self.server.journal.append(action, str(exc), owner)
            except GatewayError:
                self.reply(503, {"error": "audit-unavailable"})
                return
            status = (
                401
                if str(exc) == "unauthenticated"
                else 502 if str(exc).startswith("backend-") else 400
            )
            self.reply(status, {"error": str(exc)})
        except (ValueError, KeyError, TypeError):
            try:
                self.server.journal.append(action, "invalid-request", owner)
            except GatewayError:
                self.reply(503, {"error": "audit-unavailable"})
                return
            self.reply(400, {"error": "invalid-request"})

    do_GET = do_POST = do_DELETE = do_PUT = do_PATCH = do_OPTIONS = do_HEAD = dispatch


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GatewayError("duplicate-json-key")
        result[key] = value
    return result


def private_json(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in (0, os.geteuid())
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise GatewayError("configuration-file")
        payload = stream.read(65537)
    if len(payload) > 65536:
        raise GatewayError("configuration-size")
    return json.loads(payload, object_pairs_hook=unique_object)


def main():
    credentials = Path(os.environ.get("CREDENTIALS_DIRECTORY", ""))
    if str(credentials) != "/run/credentials/observability-silence-gateway.service":
        raise GatewayError("credential-directory")
    context = ssl.create_default_context(
        cafile=str(credentials / "silence-backend-ca.pem")
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        str(credentials / "silence-backend-client.crt"),
        str(credentials / "silence-backend-client.key"),
    )
    backend = AlertmanagerBackend("https://127.0.0.1:9093", context)
    with GatewayServer(
        ("127.0.0.1", 19094),
        private_json(credentials / "silence-policy.json"),
        private_json(credentials / "silence-auth.json"),
        backend,
        Path("/var/lib/observability-silence-gateway"),
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError):
        print("silence-gateway: runtime-refused", file=sys.stderr)
        raise SystemExit(1) from None
