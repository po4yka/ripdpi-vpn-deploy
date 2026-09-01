#!/usr/bin/env python3
"""Independent, durable provider rollback guard for Tailnet promotion.

The process owns the Terraform descriptors and a private receipt.  Its unix
socket is deliberately the only interface exposed to a promotion controller;
the controller cannot replace the planned rollback with provider API calls.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import secrets
import socket
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PROMOTION = ROOT / "scripts" / "tailnet-network-promotion.py"
MAX = 65536
IO_TIMEOUT = 5


def _promotion():
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_promotion", PROMOTION
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


p = _promotion()


class ExecutorError(RuntimeError):
    pass


def canonical(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def private_fd(path: Path, *, executable=False):
    """Open one current-user private regular file without following links."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    info = os.fstat(fd)
    allowed = 0o022 if executable else 0o077
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or info.st_mode & allowed
    ):
        os.close(fd)
        raise ExecutorError("private-input-refused")
    return fd


def _safe_directory(path: Path):
    """Require a current-user, no-follow private directory ancestry."""
    if not path.is_absolute():
        raise ExecutorError("state-directory-refused")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in {0, os.geteuid()}
                or (info.st_mode & 0o022 and not sticky_root)
            ):
                raise ExecutorError("state-directory-refused")
    except OSError:
        raise ExecutorError("state-directory-refused") from None
    finally:
        os.close(fd)


def _ensure_private_directory(path: Path):
    """Create only the final state directory below an already-safe dirfd."""
    _safe_directory(path.parent)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            os.mkdir(path.name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
    finally:
        os.close(parent)
    _safe_directory(path)


class ReceiptStore:
    """A locked canonical receipt; no request data is ever put in argv."""

    def __init__(self, root: Path):
        self.root = root
        _ensure_private_directory(root)
        _safe_directory(root)
        info = root.stat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ExecutorError("state-directory-refused")
        self.path, self.lock, self.pid = (
            root / "receipt.json",
            root / "lock",
            root / "daemon.json",
        )
        self._cleanup_stale()

    def _cleanup_stale(self):
        for stale in self.root.glob(".receipt.*.tmp"):
            info = stale.lstat()
            if (
                stat.S_ISREG(info.st_mode)
                and info.st_uid == os.geteuid()
                and info.st_nlink == 1
            ):
                stale.unlink()
            else:
                raise ExecutorError("state-directory-refused")

    def _locked(self):
        fd = os.open(
            self.lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def get(self):
        if not self.path.exists():
            return None
        fd = private_fd(self.path)
        try:
            raw = os.read(fd, MAX + 1)
        finally:
            os.close(fd)
        if len(raw) > MAX:
            raise ExecutorError("receipt-refused")
        try:
            envelope = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ExecutorError("receipt-refused") from None
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"payload", "sha256"}
            or not isinstance(envelope["sha256"], str)
            or envelope["sha256"]
            != hashlib.sha256(canonical(envelope["payload"])).hexdigest()
            or raw != canonical(envelope)
        ):
            raise ExecutorError("receipt-refused")
        value = envelope["payload"]
        if not isinstance(value, dict) or value.get("state") not in {
            "armed",
            "provider-applied",
            "committed-cleanup-debt",
            "executed",
            "released",
        }:
            raise ExecutorError("receipt-refused")
        return value

    @staticmethod
    def _write_all(fd, raw):
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise ExecutorError("receipt-write-failed")
            offset += written

    def put(self, value):
        raw = canonical(
            {"payload": value, "sha256": hashlib.sha256(canonical(value)).hexdigest()}
        )
        self._cleanup_stale()
        temporary = self.root / (".receipt." + secrets.token_hex(16) + ".tmp")
        fd = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            self._write_all(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, self.path)
        os.chmod(self.path, 0o600)
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def write_pid(self, value):
        raw = canonical(value)
        fd = os.open(
            self.pid,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            self._write_all(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)

    def clear(self):
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            return
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


class Executor:
    def __init__(self, target, state, terraform, digest, receipt_root):
        target_fd, state_fd, tf_fd = (
            private_fd(target),
            private_fd(state),
            private_fd(terraform, executable=True),
        )
        try:
            self.target = p.ProviderTarget(target_fd, state_fd)
            self.trusted = p.TrustedTerraform(tf_fd, digest)
        except BaseException:
            for fd in (target_fd, state_fd, tf_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise
        self.store = ReceiptStore(receipt_root)
        self.adapter = p.TerraformAdapter(
            self.target,
            trusted_terraform=self.trusted,
            return_path_guard=self._readback,
            external_rollback_guard=lambda *_: True,
            allow_apply=True,
        )
        # Terraform is the sole provider client.  Keep the credential only in
        # this process environment; the receipt, socket protocol and argv
        # contain identities and digests only.
        token = os.environ.get("UPCLOUD_TOKEN")
        if not token:
            self.close()
            raise ExecutorError("provider-credentials-unavailable")
        self.adapter.environment_map = {
            **self.adapter.environment_map,
            "UPCLOUD_TOKEN": token,
        }

    def close(self):
        self.adapter.close()

    def _readback(self, action, identity):
        if action != "readback":
            raise ExecutorError("return-path-refused")
        raw = self.adapter._command(["state", "pull"])
        try:
            state = json.loads(raw)
            resource = next(
                x
                for x in state["resources"]
                if x.get("type") == "upcloud_server" and x.get("name") == "vpn"
            )
            firewall = resource["instances"][0]["attributes"]["firewall"]
        except (KeyError, IndexError, StopIteration, TypeError, ValueError):
            raise ExecutorError("provider-readback-invalid") from None
        if type(firewall) is not bool:
            raise ExecutorError("provider-readback-invalid")
        return {**identity, "firewall": firewall}

    def _same(self, receipt, request, state):
        return (
            isinstance(receipt, dict)
            and receipt.get("state") == state
            and all(receipt.get(k) == v for k, v in request.items())
        )

    def _valid_current(self, value):
        base = {
            "server_uuid",
            "environment",
            "provider_target_sha256",
            "forward_plan_sha256",
            "guest_generation",
            "guest_nonce",
            "guest_snapshot_digest",
            "guest_deadline",
            "expires_at",
            "state",
        }
        state = value.get("state") if isinstance(value, dict) else None
        fields = set(base)
        if state in {"provider-applied", "committed-cleanup-debt"}:
            fields.add("provider_applied_at")
        if state == "committed-cleanup-debt":
            fields.add("promotion_observed_at")
        if state in {"executed", "released"}:
            marker = "executed_at" if state == "executed" else "released_at"
            if (
                set(value) != base | {marker}
                or not isinstance(value.get("server_uuid"), str)
                or p.UUID.fullmatch(value["server_uuid"]) is None
                or not isinstance(value.get("environment"), str)
                or p.NAME.fullmatch(value["environment"]) is None
                or not all(
                    isinstance(value.get(key), str)
                    and p.HEX.fullmatch(value[key]) is not None
                    for key in (
                        "provider_target_sha256",
                        "forward_plan_sha256",
                        "guest_nonce",
                        "guest_snapshot_digest",
                    )
                )
                or type(value.get("guest_deadline")) is not int
                or type(value.get("expires_at")) is not int
                or value["expires_at"] != value["guest_deadline"]
                or type(value.get(marker)) is not int
            ):
                raise ExecutorError("receipt-refused")
            return value
        if (
            state not in {"armed", "provider-applied", "committed-cleanup-debt"}
            or set(value) != fields
            or value.get("provider_target_sha256") != self.target.digest
            or not isinstance(value.get("environment"), str)
            or p.NAME.fullmatch(value["environment"]) is None
            or not isinstance(value.get("server_uuid"), str)
            or p.UUID.fullmatch(value["server_uuid"]) is None
            or not isinstance(value.get("guest_generation"), str)
            or p.UUID.fullmatch(value["guest_generation"]) is None
            or not all(
                isinstance(value[k], str) and p.HEX.fullmatch(value[k]) is not None
                for k in (
                    "provider_target_sha256",
                    "forward_plan_sha256",
                    "guest_nonce",
                    "guest_snapshot_digest",
                )
            )
            or type(value.get("guest_deadline")) is not int
            or type(value.get("expires_at")) is not int
            or value["expires_at"] != value["guest_deadline"]
        ):
            raise ExecutorError("receipt-refused")
        if state in {"provider-applied", "committed-cleanup-debt"} and (
            not isinstance(value.get("provider_applied_at"), int)
            or not 0 <= value["provider_applied_at"] <= value["guest_deadline"]
        ):
            raise ExecutorError("receipt-refused")
        if state == "committed-cleanup-debt" and (
            not isinstance(value.get("promotion_observed_at"), int)
            or not value["provider_applied_at"]
            <= value["promotion_observed_at"]
            <= value["guest_deadline"]
        ):
            raise ExecutorError("receipt-refused")
        return value

    def guard(self, action, request):
        if not isinstance(request, dict):
            raise ExecutorError("request-refused")
        lock = self.store._locked()
        try:
            current = self.store.get()
            if current is not None:
                self._valid_current(current)
            if action == "arm":
                fields = {
                    "server_uuid",
                    "environment",
                    "provider_target_sha256",
                    "forward_plan_sha256",
                    "guest_generation",
                    "guest_nonce",
                    "guest_snapshot_digest",
                    "guest_deadline",
                }
                if (
                    set(request) != fields
                    or request["provider_target_sha256"] != self.target.digest
                    or request["guest_deadline"] <= int(time.time())
                ):
                    raise ExecutorError("arm-refused")
                if current is not None:
                    if current["state"] not in {"executed", "released"}:
                        raise ExecutorError("arm-refused")
                    self.store.clear()
                value = {
                    **request,
                    "expires_at": request["guest_deadline"],
                    "state": "armed",
                }
                self._valid_current(value)
                self.store.put(value)
                return value
            if action == "inspect-current":
                if current is None or any(
                    current.get(k) != v for k, v in request.items()
                ):
                    raise ExecutorError("receipt-foreign")
                return current
            immutable = {
                k: v
                for k, v in request.items()
                if k
                not in {
                    "state",
                    "provider_applied_at",
                    "promotion_observed_at",
                    "_deadline_reconcile",
                }
            }
            if current is None or any(
                current.get(k) != v for k, v in immutable.items()
            ):
                raise ExecutorError("receipt-foreign")
            if action == "inspect":
                return current
            if (
                action == "mark-applied"
                and current["state"] == "armed"
                and type(request.get("provider_applied_at")) is int
            ):
                value = {**request, "state": "provider-applied"}
                self.store.put(value)
                return value
            if (
                action == "commit"
                and current["state"] == "provider-applied"
                and type(request.get("promotion_observed_at")) is int
            ):
                value = {**request, "state": "committed-cleanup-debt"}
                self.store.put(value)
                return value
            if action == "release" and current["state"] == "committed-cleanup-debt":
                value = {
                    **current,
                    "state": "released",
                    "released_at": int(time.time()),
                }
                value.pop("provider_applied_at")
                value.pop("promotion_observed_at")
                self._valid_current(value)
                self.store.put(value)
                return {"state": "released"}
            if action == "execute" and current["state"] == "executed":
                return {"state": "executed"}
            if (
                action == "execute"
                and current["state"] in {"armed", "provider-applied"}
                and (
                    current["expires_at"] > int(time.time())
                    or request.get("_deadline_reconcile") is True
                )
            ):
                plan = self.adapter.plan("rollback")
                try:
                    # This daemon alone owns the armed receipt and invokes the
                    # canonical Terraform false transition after recovery.
                    self.adapter._rollback_armed = True
                    self.adapter.apply("rollback", plan)
                finally:
                    plan.close()
                value = {
                    **current,
                    "state": "executed",
                    "executed_at": int(time.time()),
                }
                value.pop("provider_applied_at", None)
                self._valid_current(value)
                self.store.put(value)
                return {"state": "executed"}
            raise ExecutorError("transition-refused")
        finally:
            os.close(lock)

    def reconcile(self):
        current = self.store.get()
        if current is not None:
            self._valid_current(current)
        if (
            current
            and current.get("state") in {"armed", "provider-applied"}
            and current.get("expires_at", 0) <= int(time.time())
        ):
            # A missed deadline is unsafe: perform the independent false apply.
            request = {**current, "_deadline_reconcile": True}
            return self.guard("execute", request)


def serve(args):
    executor = Executor(
        Path(args.target),
        Path(args.state),
        Path(args.terraform),
        args.terraform_sha256,
        Path(args.receipt_dir),
    )
    path = Path(args.socket)
    _safe_directory(path.parent)
    if path.exists() or path.is_symlink():
        raise ExecutorError("socket-refused")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        executor.store.write_pid(
            {
                "schema_version": 1,
                "pid": os.getpid(),
                "provider_target_sha256": executor.target.digest,
            }
        )
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(8)
        listener.setblocking(False)
        while True:
            ready, _, _ = select.select([listener], [], [], 1)
            if not ready:
                try:
                    executor.reconcile()
                except (ExecutorError, p.PromotionError):
                    pass
                continue
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(IO_TIMEOUT)
                    chunks = bytearray()
                    while len(chunks) <= MAX:
                        chunk = connection.recv(min(4096, MAX + 1 - len(chunks)))
                        if not chunk:
                            break
                        chunks.extend(chunk)
                    terminal = False
                    try:
                        request = json.loads(bytes(chunks))
                        if request.get("action") == "ping":
                            result = {"provider_target_sha256": executor.target.digest}
                        else:
                            result = executor.guard(request["action"], request["value"])
                            terminal = request.get("action") in {
                                "execute",
                                "release",
                            } and result.get("state") in {"executed", "released"}
                        response = canonical({"ok": result})
                    except (
                        ExecutorError,
                        p.PromotionError,
                        KeyError,
                        TypeError,
                        ValueError,
                        UnicodeError,
                    ):
                        response = canonical({"error": "rollback-uncertain"})
                    try:
                        connection.sendall(response)
                    except (BrokenPipeError, ConnectionError, socket.timeout):
                        pass
                    if terminal:
                        break
            except (OSError, socket.timeout):
                # A hostile or partial client must not prevent deadline recovery.
                continue
    finally:
        listener.close()
        executor.close()
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        try:
            executor.store.pid.unlink()
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("serve")
    parser.add_argument("--target", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--terraform", required=True)
    parser.add_argument("--terraform-sha256", required=True)
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    try:
        serve(args)
    except (ExecutorError, p.PromotionError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
