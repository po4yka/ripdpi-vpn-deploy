#!/usr/bin/env python3
"""Fail-closed one-node Tailnet/provider promotion core.

This is deliberately an import-only core.  A future operator entry point must
inject its reviewed return-path and external rollback guards; constructing the
adapter alone grants no Terraform apply authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time

import fleet_inspection
from sshd_contexts import ContextError, bind_contexts

ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_ENV = ROOT / "scripts" / "terraform-env.sh"
MAX_OUTPUT = 1_048_576
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
HEX = re.compile(r"[0-9a-f]{64}\Z")


class PromotionError(RuntimeError):
    """Only categorical, secret-free failures cross this boundary."""


def _json(raw: bytes):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (UnicodeError, ValueError, json.JSONDecodeError):
        raise PromotionError("provider-plan-invalid") from None


def _write_all(fd, payload):
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise PromotionError("terraform-executable-invalid")
        offset += written


def _env(environment: str) -> dict[str, str]:
    if not isinstance(environment, str) or NAME.fullmatch(environment) is None:
        raise PromotionError("provider-target-invalid")
    # terraform-env.sh is the authority for provider root, workspace and
    # TF_DATA_DIR.  Keep only locale/PATH plus its literal selector.
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PROVIDER": "upcloud",
        "ENV": environment,
    }


def _bounded(
    command, environment, *, input_data=None, timeout=90, pass_fds=()
) -> bytes:
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            start_new_session=True,
            pass_fds=pass_fds,
        )
    except OSError as error:
        raise PromotionError("provider-command-unavailable") from error
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stdin):
                if stream is None:
                    continue
                os.set_blocking(stream.fileno(), False)
                selector.register(
                    stream,
                    (
                        selectors.EVENT_READ
                        if stream is process.stdout
                        else selectors.EVENT_WRITE
                    ),
                )
            sent = 0
            data = input_data or b""
            if not data and process.stdin is not None:
                selector.unregister(process.stdin)
                process.stdin.close()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PromotionError("provider-command-timeout")
                for key, events in selector.select(remaining):
                    if key.fileobj is process.stdout:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            output.extend(chunk)
                            if len(output) > MAX_OUTPUT:
                                raise PromotionError("provider-output-limit")
                    elif events & selectors.EVENT_WRITE:
                        try:
                            written = os.write(key.fd, data[sent:])
                            if written <= 0:
                                raise PromotionError("provider-command-failed")
                            sent += written
                        except BrokenPipeError:
                            # The bounded child closed stdin before consuming
                            # the request; its exit status remains authoritative.
                            sent = len(data)
                        if sent == len(data):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
            if process.wait(max(0.001, deadline - time.monotonic())) != 0:
                raise PromotionError("provider-command-failed")
            return bytes(output)
    except subprocess.TimeoutExpired:
        raise PromotionError("provider-command-timeout") from None
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                # The owned process group exited between poll and cleanup.
                pass
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                stream.close()


class SavedPlan:
    """A private, unlinked plan inode; close is idempotent and one-shot."""

    __slots__ = ("fd", "digest", "size", "_closed")

    def __init__(self, fd: int):
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 0
            or not 0 < info.st_size <= MAX_OUTPUT
        ):
            os.close(fd)
            raise PromotionError("provider-plan-unsafe")
        os.lseek(fd, 0, os.SEEK_SET)
        payload = os.read(fd, MAX_OUTPUT + 1)
        if len(payload) != info.st_size:
            os.close(fd)
            raise PromotionError("provider-plan-unsafe")
        self.fd, self.digest, self.size, self._closed = (
            fd,
            hashlib.sha256(payload).hexdigest(),
            info.st_size,
            False,
        )

    def path(self) -> str:
        if self._closed:
            raise PromotionError("provider-plan-closed")
        return (
            "/dev/fd/" if platform.system() == "Darwin" else "/proc/self/fd/"
        ) + str(self.fd)

    def verify(self):
        if self._closed:
            raise PromotionError("provider-plan-closed")
        info = os.fstat(self.fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 0
            or info.st_size != self.size
        ):
            raise PromotionError("provider-plan-unsafe")
        os.lseek(self.fd, 0, os.SEEK_SET)
        if hashlib.sha256(os.read(self.fd, self.size + 1)).hexdigest() != self.digest:
            raise PromotionError("provider-plan-unsafe")

    def close(self):
        if not self._closed:
            os.close(self.fd)
            self._closed = True


class TrustedTerraform:
    """A caller-reviewed Terraform executable, pinned by open inode digest."""

    __slots__ = ("fd", "digest", "_closed")

    def __init__(self, fd: int, digest: str):
        if not isinstance(digest, str) or HEX.fullmatch(digest) is None:
            raise PromotionError("terraform-executable-invalid")
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise PromotionError("terraform-executable-invalid")
        if info.st_size <= 0 or self._digest(fd) != digest:
            raise PromotionError("terraform-executable-invalid")
        self.fd, self.digest, self._closed = fd, digest, False

    def path(self):
        if self._closed:
            raise PromotionError("terraform-executable-invalid")
        return (
            "/dev/fd/" if platform.system() == "Darwin" else "/proc/self/fd/"
        ) + str(self.fd)

    def verify(self):
        if self._closed:
            raise PromotionError("terraform-executable-invalid")
        if self._digest(self.fd) != self.digest:
            raise PromotionError("terraform-executable-invalid")

    def close(self):
        if not self._closed:
            os.close(self.fd)
            self._closed = True

    def install(self, root: Path):
        """Materialize the reviewed FD into a private executable root.

        Darwin cannot exec an O_RDONLY /dev/fd entry.  A mode-0700 temporary
        root retains the FD/digest trust chain without relying on PATH state.
        """
        self.verify()
        path = root / "terraform"
        fd = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o700,
        )
        try:
            os.lseek(self.fd, 0, os.SEEK_SET)
            while chunk := os.read(self.fd, 1_048_576):
                _write_all(fd, chunk)
            os.fsync(fd)
            os.fchmod(fd, 0o700)
        finally:
            os.close(fd)
        copy = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if self._digest(copy) != self.digest:
                raise PromotionError("terraform-executable-invalid")
        finally:
            os.close(copy)

    @staticmethod
    def _digest(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1_048_576):
            digest.update(chunk)
        return digest.hexdigest()


class ProviderTarget:
    """Private state-backed binding between one inventory node and provider state."""

    __slots__ = ("fd", "state_fd", "raw", "state_raw", "digest", "value", "_closed")

    def __init__(self, fd: int, state_fd: int):
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 0 < info.st_size <= 4096
        ):
            raise PromotionError("provider-target-invalid")
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 4097)
        try:
            value = json.loads(raw)
            fields = {
                "schema_version",
                "provider",
                "environment",
                "server_uuid",
                "inventory_alias",
                "public_service_address_sha256",
                "deployable_digest",
                "state_sha256",
            }
            canonical = (
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            if (
                set(value) != fields
                or raw != canonical
                or value["schema_version"] != 1
                or value["provider"] != "upcloud"
                or NAME.fullmatch(value["environment"]) is None
                or NAME.fullmatch(value["inventory_alias"]) is None
                or UUID.fullmatch(value["server_uuid"]) is None
                or any(
                    HEX.fullmatch(value[key]) is None
                    for key in (
                        "public_service_address_sha256",
                        "deployable_digest",
                        "state_sha256",
                    )
                )
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise PromotionError("provider-target-invalid") from None
        state_info = os.fstat(state_fd)
        if (
            not stat.S_ISREG(state_info.st_mode)
            or state_info.st_uid != os.geteuid()
            or stat.S_IMODE(state_info.st_mode) != 0o600
            or state_info.st_nlink != 1
            or not 0 < state_info.st_size <= MAX_OUTPUT
        ):
            raise PromotionError("provider-target-invalid")
        os.lseek(state_fd, 0, os.SEEK_SET)
        state_raw = os.read(state_fd, MAX_OUTPUT + 1)
        try:
            state = json.loads(state_raw)
            matches = [
                item
                for item in state["resources"]
                if item.get("mode") == "managed"
                and item.get("type") == "upcloud_server"
                and item.get("name") == "vpn"
            ]
            instances = matches[0]["instances"]
            address = state["outputs"]["server_ipv4"]["value"]
            if (
                len(matches) != 1
                or len(instances) != 1
                or not isinstance(address, str)
                or instances[0]["attributes"].get("id") != value["server_uuid"]
                or hashlib.sha256(address.encode()).hexdigest()
                != value["public_service_address_sha256"]
                or hashlib.sha256(state_raw).hexdigest() != value["state_sha256"]
            ):
                raise ValueError
        except (
            IndexError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            raise PromotionError("provider-target-invalid") from None
        (
            self.fd,
            self.state_fd,
            self.raw,
            self.state_raw,
            self.digest,
            self.value,
            self._closed,
        ) = (
            fd,
            state_fd,
            raw,
            state_raw,
            hashlib.sha256(raw).hexdigest(),
            value,
            False,
        )

    def verify(self):
        if self._closed:
            raise PromotionError("provider-target-invalid")
        info = os.fstat(self.fd)
        state_info = os.fstat(self.state_fd)
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.lseek(self.state_fd, 0, os.SEEK_SET)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size != len(self.raw)
            or os.read(self.fd, len(self.raw) + 1) != self.raw
            or not stat.S_ISREG(state_info.st_mode)
            or state_info.st_uid != os.geteuid()
            or stat.S_IMODE(state_info.st_mode) != 0o600
            or state_info.st_nlink != 1
            or state_info.st_size != len(self.state_raw)
            or os.read(self.state_fd, len(self.state_raw) + 1) != self.state_raw
        ):
            raise PromotionError("provider-target-invalid")

    def close(self):
        if not self._closed:
            os.close(self.fd)
            os.close(self.state_fd)
            self._closed = True


class TerraformAdapter:
    """Canonical UpCloud adapter.  `allow_apply` is intentionally false by default."""

    def __init__(
        self,
        target: ProviderTarget,
        *,
        trusted_terraform: TrustedTerraform | None = None,
        return_path_guard=None,
        external_rollback_guard=None,
        provider_transaction_lock=None,
        allow_apply=False,
    ):
        if not isinstance(target, ProviderTarget):
            raise PromotionError("provider-target-invalid")
        target.verify()
        self.target = target
        self.environment, self.server_uuid = (
            target.value["environment"],
            target.value["server_uuid"],
        )
        self.environment_map = _env(self.environment)
        self.return_path_guard, self.external_rollback_guard = (
            return_path_guard,
            external_rollback_guard,
        )
        self.provider_transaction_lock = provider_transaction_lock
        self.allow_apply = allow_apply
        self.trusted_terraform = trusted_terraform
        self._plans: set[SavedPlan] = set()
        self._rollback_armed = False
        self._rollback_receipt = None
        self._cleanup_receipt = None
        self._forward_lock_fd = -1

    def close(self):
        self._release_forward_lock()
        for plan in tuple(self._plans):
            plan.close()
        self._plans.clear()
        self.target.close()
        if self.trusted_terraform is not None:
            self.trusted_terraform.close()

    def _release_forward_lock(self):
        if self._forward_lock_fd >= 0:
            os.close(self._forward_lock_fd)
            self._forward_lock_fd = -1

    def bind_target(self, identity, target_digest):
        self.target.verify()
        expected = {
            "inventory_alias": self.target.value["inventory_alias"],
            "public_service_address_sha256": self.target.value[
                "public_service_address_sha256"
            ],
            "deployable_digest": self.target.value["deployable_digest"],
        }
        if identity != expected or target_digest != self.target.digest:
            raise PromotionError("provider-target-mismatch")
        return True

    def _guard_identity(self):
        self.target.verify()
        return {
            "server_uuid": self.server_uuid,
            "environment": self.environment,
            "provider_target_sha256": self.target.digest,
        }

    def _verify_initial_state(self):
        self.target.verify()
        current = self._command(["state", "pull"])
        if hashlib.sha256(current).hexdigest() != self.target.value["state_sha256"]:
            raise PromotionError("provider-state-drift")

    def _command(self, arguments, *, pass_fds=()):
        if not isinstance(self.trusted_terraform, TrustedTerraform):
            raise PromotionError("terraform-executable-not-trusted")
        self.trusted_terraform.verify()
        with tempfile.TemporaryDirectory(prefix="vpn-tailnet-bin-") as binary_directory:
            os.chmod(binary_directory, 0o700)
            self.trusted_terraform.install(Path(binary_directory))
            environment = {
                **self.environment_map,
                "PATH": binary_directory + ":/usr/bin:/bin:/usr/sbin:/sbin",
            }
            return _bounded(
                [str(TERRAFORM_ENV), *arguments], environment, pass_fds=pass_fds
            )

    def _save(self, direction: str) -> SavedPlan:
        if direction not in {"forward", "rollback"}:
            raise PromotionError("provider-plan-invalid")
        before, after = (
            ("false", "true") if direction == "forward" else ("true", "false")
        )
        if direction == "forward":
            self._verify_initial_state()
        else:
            self.target.verify()
            self._readback(True)
        with tempfile.TemporaryDirectory(prefix="vpn-tailnet-plan-") as directory:
            os.chmod(directory, 0o700)
            name = str(Path(directory) / "plan")
            self._command(
                [
                    "plan",
                    "-input=false",
                    "-refresh=true",
                    "-out",
                    name,
                    "-var",
                    f"enable_provider_firewall={after}",
                ]
            )
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise PromotionError("provider-plan-unsafe")
                os.fchmod(fd, 0o600)
                os.unlink(name)
                plan = SavedPlan(fd)
                fd = -1
                show = self._command(
                    ["show", "-json", plan.path()], pass_fds=(plan.fd,)
                )
                review_plan(show, self.server_uuid, before == "true", after == "true")
                self._plans.add(plan)
                return plan
            finally:
                if fd >= 0:
                    os.close(fd)

    def plan(self, direction: str) -> SavedPlan:
        return self._save(direction)

    def arm_rollback(self, forward, guest_receipt):
        if not callable(self.external_rollback_guard):
            raise PromotionError("provider-apply-not-authorized")
        forward.verify()
        guest_identity = _receipt(guest_receipt, "prepared")
        if guest_identity["deadline"] <= int(time.time()):
            raise PromotionError("guest-uncertain")
        request = {
            **self._guard_identity(),
            "forward_plan_sha256": forward.digest,
            "guest_generation": guest_identity["generation"],
            "guest_nonce": guest_identity["nonce"],
            "guest_snapshot_digest": guest_identity["snapshot_digest"],
            "guest_deadline": guest_identity["deadline"],
        }
        receipt = self.external_rollback_guard("arm", request)
        if (
            not isinstance(receipt, dict)
            or set(receipt) != {*request, "expires_at", "state"}
            or any(receipt[key] != value for key, value in request.items())
            or type(receipt["expires_at"]) is not int
            or not int(time.time())
            < receipt["expires_at"]
            <= guest_identity["deadline"]
            or receipt["state"] != "armed"
        ):
            raise PromotionError("provider-rollback-not-armed")
        self._rollback_receipt = tuple(sorted(receipt.items()))
        self._rollback_armed = True
        return self._rollback_receipt

    def _readback(self, expected):
        request = self._guard_identity()
        result = self.return_path_guard("readback", request)
        if result != {**request, "firewall": expected}:
            raise PromotionError("provider-readback-invalid")

    def readback(self, expected):
        self._readback(expected)

    def _hydrate(self, capability, state):
        try:
            value = dict(capability)
            fields = {
                *self._guard_identity(),
                "forward_plan_sha256",
                "expires_at",
                "state",
                "guest_generation",
                "guest_nonce",
                "guest_snapshot_digest",
                "guest_deadline",
            }
            if state in {
                "forward-started",
                "provider-applied",
                "committed-cleanup-debt",
            }:
                fields.add("forward_lease")
            if state in {"provider-applied", "committed-cleanup-debt"}:
                fields.add("provider_applied_at")
            if state == "committed-cleanup-debt":
                fields.add("promotion_observed_at")
            if (
                not isinstance(capability, (tuple, list))
                or set(value) != fields
                or any(
                    value[key] != expected
                    for key, expected in self._guard_identity().items()
                )
                or HEX.fullmatch(value["forward_plan_sha256"]) is None
                or type(value["expires_at"]) is not int
                or value["expires_at"] <= int(time.time())
                or value["state"] != state
                or UUID.fullmatch(value["guest_generation"]) is None
                or HEX.fullmatch(value["guest_nonce"]) is None
                or HEX.fullmatch(value["guest_snapshot_digest"]) is None
                or type(value["guest_deadline"]) is not int
                or value["guest_deadline"] < 0
                or (
                    state in {"armed", "forward-started", "provider-applied"}
                    and value["guest_deadline"] <= int(time.time())
                )
                or (
                    state in {"provider-applied", "committed-cleanup-debt"}
                    and (
                        type(value["provider_applied_at"]) is not int
                        or not 0
                        <= value["provider_applied_at"]
                        <= value["guest_deadline"]
                    )
                )
                or (
                    state == "committed-cleanup-debt"
                    and (
                        type(value["promotion_observed_at"]) is not int
                        or not value["provider_applied_at"]
                        <= value["promotion_observed_at"]
                        <= value["guest_deadline"]
                    )
                )
                or self.external_rollback_guard("inspect", value) != value
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise PromotionError("rollback-uncertain") from None
        result = tuple(sorted(value.items()))
        if state in {"armed", "forward-started", "provider-applied"}:
            self._rollback_receipt, self._rollback_armed = result, True
        else:
            self._cleanup_receipt, self._rollback_armed = result, False
        return result

    def hydrate_armed(self, capability):
        return self._hydrate(capability, "armed")

    def hydrate_cleanup(self, capability):
        return self._hydrate(capability, "committed-cleanup-debt")

    def hydrate_current(self, armed_capability):
        """Resolve the durable guard state by the immutable arm identity."""
        armed = dict(armed_capability)
        try:
            if armed.get("state") != "armed":
                raise ValueError
            request = {key: value for key, value in armed.items() if key != "state"}
            current = self.external_rollback_guard("inspect-current", request)
            if not isinstance(current, dict):
                raise ValueError
            capability = tuple(sorted(current.items()))
            state = current.get("state")
            if state == "armed":
                return self.hydrate_armed(capability)
            if state == "forward-started":
                return self._hydrate(capability, "forward-started")
            if state == "provider-applied":
                return self._hydrate(capability, "provider-applied")
            if state == "committed-cleanup-debt":
                return self.hydrate_cleanup(capability)
            raise ValueError
        except (KeyError, TypeError, ValueError):
            raise PromotionError("rollback-uncertain") from None

    def mark_applied(self, capability, applied_at):
        if capability != self._rollback_receipt or not self._rollback_armed:
            raise PromotionError("rollback-uncertain")
        armed = dict(capability)
        if (
            armed.get("state") != "forward-started"
            or type(applied_at) is not int
            or not 0 <= applied_at < armed["guest_deadline"]
        ):
            raise PromotionError("rollback-uncertain")
        request = {key: value for key, value in armed.items() if key != "state"} | {
            "provider_applied_at": applied_at
        }
        result = self.external_rollback_guard("mark-applied", request)
        expected = {**request, "state": "provider-applied"}
        if result != expected:
            raise PromotionError("rollback-uncertain")
        self._rollback_receipt = tuple(sorted(result.items()))
        return self._rollback_receipt

    def begin_forward(self, capability):
        if capability != self._rollback_receipt or not self._rollback_armed:
            raise PromotionError("rollback-uncertain")
        armed = dict(capability)
        if armed.get("state") != "armed":
            raise PromotionError("rollback-uncertain")
        request = {key: value for key, value in armed.items() if key != "state"}
        result = self.external_rollback_guard("begin-forward", request)
        expected = {**request, "state": "forward-started"}
        if (
            not isinstance(result, dict)
            or set(result) != {*expected, "forward_lease"}
            or any(result[key] != value for key, value in expected.items())
            or HEX.fullmatch(result["forward_lease"]) is None
        ):
            raise PromotionError("rollback-uncertain")
        if not callable(self.provider_transaction_lock):
            raise PromotionError("rollback-uncertain")
        lock = self.provider_transaction_lock()
        if type(lock) is not int or lock < 0:
            raise PromotionError("rollback-uncertain")
        try:
            # The provider lock is shared with deadline reconciliation.  Re-read
            # the exact durable lease after acquiring it, before Terraform can
            # make the public change.
            if self.external_rollback_guard("inspect", result) != result or result[
                "expires_at"
            ] <= int(time.time()):
                raise PromotionError("rollback-uncertain")
        except (Exception, KeyboardInterrupt, SystemExit):
            os.close(lock)
            raise
        self._forward_lock_fd = lock
        self._rollback_receipt = tuple(sorted(result.items()))
        return self._rollback_receipt

    def apply_forward(self, capability, plan, applied_at):
        try:
            if (
                capability != self._rollback_receipt
                or self._forward_lock_fd < 0
                or dict(capability).get("state") != "forward-started"
                or dict(capability).get("expires_at", 0) <= int(time.time())
            ):
                raise PromotionError("rollback-uncertain")
            self.apply("forward", plan)
            return self.mark_applied(capability, applied_at)
        finally:
            self._release_forward_lock()

    def external_rollback(self, capability):
        if not self._rollback_armed:
            raise PromotionError("rollback-uncertain")
        if (
            capability != self._rollback_receipt
            or dict(capability)["expires_at"] <= int(time.time())
            or self.external_rollback_guard("execute", dict(capability))
            != {"state": "executed"}
        ):
            raise PromotionError("rollback-uncertain")
        self._readback(False)

    def release_rollback(self, capability):
        if (
            capability != self._cleanup_receipt
            or dict(capability)["expires_at"] <= int(time.time())
            or self.external_rollback_guard("release", dict(capability))
            != {"state": "released"}
        ):
            raise PromotionError("rollback-uncertain")
        self._cleanup_receipt = None

    def validate_promotion_proof(self, proof_receipt, capability=None):
        expected_target = {
            "inventory_alias": self.target.value["inventory_alias"],
            "public_service_address_sha256": self.target.value[
                "public_service_address_sha256"
            ],
            "deployable_digest": self.target.value["deployable_digest"],
        }
        if (
            not isinstance(proof_receipt, dict)
            or set(proof_receipt)
            != {"schema_version", "status", "target_identity", "observed_at"}
            or proof_receipt.get("schema_version") != 1
            or proof_receipt.get("status") != "passed"
            or proof_receipt.get("target_identity") != expected_target
            or type(proof_receipt.get("observed_at")) is not int
            or not 0 <= proof_receipt["observed_at"] <= int(time.time())
            or (
                capability is not None
                and (
                    capability.get("promotion_observed_at")
                    != proof_receipt["observed_at"]
                    or capability.get(
                        "provider_applied_at", proof_receipt["observed_at"] + 1
                    )
                    > proof_receipt["observed_at"]
                    or proof_receipt["observed_at"]
                    > capability.get("guest_deadline", -1)
                )
            )
        ):
            raise PromotionError("rollback-uncertain")

    def commit_rollback(self, capability, guest_receipt, proof_receipt):
        if capability != self._rollback_receipt or not self._rollback_armed:
            raise PromotionError("rollback-uncertain")
        guest_identity = _receipt(guest_receipt, "committed")
        self.validate_promotion_proof(proof_receipt)
        armed = dict(capability)
        if armed.get("state") != "provider-applied":
            raise PromotionError("rollback-uncertain")
        if any(
            armed["guest_" + key] != guest_identity[key]
            for key in ("generation", "nonce", "snapshot_digest", "deadline")
        ):
            raise PromotionError("rollback-uncertain")
        if armed["expires_at"] <= int(time.time()):
            raise PromotionError("rollback-uncertain")
        if (
            not armed["provider_applied_at"]
            <= proof_receipt["observed_at"]
            <= armed["guest_deadline"]
        ):
            raise PromotionError("rollback-uncertain")
        request = {key: armed[key] for key in armed if key != "state"} | {
            "promotion_observed_at": proof_receipt["observed_at"]
        }
        result = self.external_rollback_guard("commit", request)
        expected = {**request, "state": "committed-cleanup-debt"}
        if result != expected:
            raise PromotionError("rollback-uncertain")
        self._cleanup_receipt = tuple(sorted(result.items()))
        self._rollback_receipt, self._rollback_armed = None, False
        return self._cleanup_receipt

    def apply(self, direction: str, plan: SavedPlan):
        if (
            not self.allow_apply
            or not callable(self.return_path_guard)
            or not callable(self.external_rollback_guard)
        ):
            raise PromotionError("provider-apply-not-authorized")
        if not self._rollback_armed:
            raise PromotionError("provider-rollback-not-armed")
        if (
            direction == "forward"
            and self.return_path_guard("forward", self._guard_identity()) is not True
        ):
            raise PromotionError("provider-return-path-invalid")
        if plan not in self._plans:
            raise PromotionError("provider-plan-unknown")
        if direction == "forward":
            self._verify_initial_state()
        else:
            self.target.verify()
            self._readback(True)
        plan.verify()
        self._command(
            ["apply", "-input=false", "-auto-approve", plan.path()], pass_fds=(plan.fd,)
        )
        self._readback(direction == "forward")
        self._plans.remove(plan)
        plan.close()


def review_plan(raw: bytes, server_uuid: str, before: bool, after: bool):
    doc = _json(raw)
    try:
        if doc.get("format_version") != "1.2":
            raise ValueError
        changes = doc["resource_changes"]
        if not isinstance(changes, list):
            raise ValueError
        expected = {
            "upcloud_server.vpn": ("upcloud_server", "vpn"),
            "upcloud_firewall_rules.vpn": ("upcloud_firewall_rules", "vpn"),
            "terraform_data.ssh_port": ("terraform_data", "ssh_port"),
        }
        if any(
            item.get("address") not in expected
            or (item.get("type"), item.get("name")) != expected[item.get("address")]
            or item["change"].get("actions") == ["no-op"]
            and (
                item["change"].get("before") != item["change"].get("after")
                or item["change"].get("after_unknown") != {}
            )
            for item in changes
        ):
            raise ValueError
        dirty = [item for item in changes if item["change"]["actions"] != ["no-op"]]
        if len(dirty) != 1 or {item.get("address") for item in changes} != set(
            expected
        ):
            raise ValueError
        item = dirty[0]
        change = item["change"]
        if (
            item["address"] != "upcloud_server.vpn"
            or item["type"] != "upcloud_server"
            or item["name"] != "vpn"
            or change["actions"] != ["update"]
        ):
            raise ValueError
        if change.get("after_unknown") != {}:
            raise ValueError
        old, new = dict(change["before"]), dict(change["after"])
        if (
            old.pop("firewall") is not before
            or new.pop("firewall") is not after
            or old != new
            or old.get("id") != server_uuid
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise PromotionError("provider-plan-invalid") from None


def _receipt(value, status):
    if (
        not isinstance(value, dict)
        or set(value)
        != {"status", "generation", "nonce", "snapshot_digest", "deadline"}
        or value.get("status") != status
        or UUID.fullmatch(value.get("generation", "")) is None
        or HEX.fullmatch(value.get("nonce", "")) is None
        or HEX.fullmatch(value.get("snapshot_digest", "")) is None
        or type(value.get("deadline")) is not int
        or value["deadline"] < 0
    ):
        raise PromotionError("guest-uncertain")
    return {
        key: value[key]
        for key in ("generation", "nonce", "snapshot_digest", "deadline")
    }


def _same_receipt(value, identity, status):
    if _receipt(value, status) != identity:
        raise PromotionError("guest-uncertain")


def reconcile_release(adapter, capability):
    """Explicit retry for a committed release-cleanup debt; expiry fails closed."""
    adapter.hydrate_cleanup(capability)
    adapter.release_rollback(capability)
    return {"status": "committed"}


def reconcile_commit_release(adapter, armed_capability, guest_receipt, proof_receipt):
    """Finish a post-confirm crash without releasing an ordinary armed lease."""
    current = adapter.hydrate_current(armed_capability)
    if dict(current)["state"] == "committed-cleanup-debt":
        # Revalidate the persisted evidence before releasing an already
        # committed guard transition whose local response was lost.
        guest = _receipt(guest_receipt, "committed")
        value = dict(current)
        if any(
            value["guest_" + key] != guest[key]
            for key in ("generation", "nonce", "snapshot_digest", "deadline")
        ):
            raise PromotionError("rollback-uncertain")
        adapter.validate_promotion_proof(proof_receipt, value)
        cleanup = current
    else:
        cleanup = adapter.commit_rollback(current, guest_receipt, proof_receipt)
    adapter.release_rollback(cleanup)
    return {"status": "committed"}


def promotion_proof(
    config: Path,
    environment: dict[str, str],
    expected_identity: dict,
    applied_after: int,
):
    """Invoke the independent proof program once and accept its safe receipt."""
    output = _bounded(
        [
            sys.executable,
            str(ROOT / "scripts" / "sshd-promotion-proof.py"),
            "--config",
            str(config),
        ],
        environment,
        timeout=615,
    )
    try:
        receipt = _json(output)
        identity = receipt["target_identity"]
        if (
            set(receipt)
            == {"schema_version", "status", "target_identity", "observed_at"}
            and receipt["schema_version"] == 1
            and receipt["status"] == "passed"
            and type(applied_after) is int
            and type(receipt["observed_at"]) is int
            and applied_after <= receipt["observed_at"] <= int(time.time())
            and identity == expected_identity
        ):
            return receipt
        return None
    except (KeyError, TypeError, ValueError, UnicodeError, PromotionError):
        return None


def _execute(
    request: dict,
    adapter: TerraformAdapter,
    *,
    guest,
    known_hosts: Path,
    environment=None,
    selected_host=None,
):
    """Run exactly one selected node; the caller supplies bounded guest RPCs."""
    try:
        if (
            set(request)
            != {
                "inventory_path",
                "inventory_name",
                "contexts",
                "mode",
                "promotion_config_path",
                "target_identity",
                "provider_target_sha256",
            }
            or request["mode"] not in {"dry-run", "apply"}
            or not isinstance(request["promotion_config_path"], str)
        ):
            raise ValueError
        if selected_host is None:
            hosts = fleet_inspection.select_hosts(
                Path(request["inventory_path"]), [request["inventory_name"]]
            )
            if len(hosts) != 1:
                raise ValueError
            host = hosts[0]
        elif not isinstance(selected_host, dict):
            raise ValueError
        else:
            host = selected_host
        bind_contexts(
            request["contexts"], host["address"], host["transport"], host["port"]
        )
        expected_identity = request["target_identity"]
        if (
            not isinstance(expected_identity, dict)
            or set(expected_identity)
            != {"inventory_alias", "public_service_address_sha256", "deployable_digest"}
            or expected_identity["inventory_alias"] != host["name"]
            or expected_identity["public_service_address_sha256"]
            != hashlib.sha256(host["address"].encode()).hexdigest()
            or HEX.fullmatch(expected_identity["deployable_digest"]) is None
            or HEX.fullmatch(request["provider_target_sha256"]) is None
        ):
            raise ValueError
        adapter.bind_target(expected_identity, request["provider_target_sha256"])
    except (ValueError, KeyError, fleet_inspection.InspectionError, ContextError):
        raise PromotionError("request-invalid") from None
    forward = adapter.plan("forward")
    if request["mode"] == "dry-run":
        forward.close()
        adapter._plans.discard(forward)
        return {"status": "dry-run"}
    identity = None
    rollback = None
    capability = None
    provider_started = False
    committed = False
    try:
        prepared = guest(host, "prepare", {}, False)
        identity = _receipt(prepared, "prepared")
        capability = adapter.arm_rollback(forward, prepared)
        provider_started = True
        capability = adapter.begin_forward(capability)
        capability = adapter.apply_forward(capability, forward, int(time.time()))
        rollback = adapter.plan("rollback")
        _same_receipt(guest(host, "apply", identity, False), identity, "applied")
        applied_after = dict(capability)["provider_applied_at"]
        # Fresh public SFTP must precede the new Tailnet SFTP. ssh_command and
        # sftp_command preserve the same pinned HostKeyAlias independently.
        public = dict(host, transport=host["address"])
        for transport in (public, host):
            _bounded(
                fleet_inspection.ssh_command(transport, known_hosts),
                environment or _env(adapter.environment),
                input_data=b"",
                timeout=30,
            )
            _bounded(
                fleet_inspection.sftp_command(transport, known_hosts),
                environment or _env(adapter.environment),
                input_data=b"pwd\nquit\n",
                timeout=30,
            )
        proof_result = promotion_proof(
            Path(request["promotion_config_path"]),
            environment or _env(adapter.environment),
            expected_identity,
            applied_after,
        )
        if proof_result is None:
            raise PromotionError("promotion-proof-failed")
        _same_receipt(guest(host, "status", {}, False), identity, "applied")
        adapter.readback(True)
        confirmed = guest(host, "confirm", identity, False)
        _same_receipt(confirmed, identity, "committed")
        committed = True
        try:
            cleanup = adapter.commit_rollback(capability, confirmed, proof_result)
        except (Exception, KeyboardInterrupt, SystemExit):
            return {
                "status": "committed-rollback-armed",
                "rollback_capability": capability,
                "guest_receipt": confirmed,
                "promotion_receipt": proof_result,
            }
        try:
            adapter.release_rollback(cleanup)
        except (Exception, KeyboardInterrupt, SystemExit):
            return {"status": "committed-cleanup-debt", "rollback_capability": cleanup}
        rollback.close()
        adapter._plans.discard(rollback)
        return {"status": "committed"}
    except (Exception, KeyboardInterrupt, SystemExit):
        if committed:
            return {
                "status": "committed-rollback-armed",
                "rollback_capability": capability,
            }
        try:
            if identity is not None:
                if provider_started:
                    if rollback is None:
                        adapter.external_rollback(capability)
                    else:
                        try:
                            adapter.apply("rollback", rollback)
                        except (Exception, KeyboardInterrupt, SystemExit):
                            adapter.external_rollback(capability)
                _same_receipt(
                    guest(host, "rollback", identity, True), identity, "rolled_back"
                )
        except (Exception, KeyboardInterrupt, SystemExit):
            raise PromotionError("rollback-uncertain") from None
        raise
    finally:
        # Saved plans are capabilities too; close them before the adapter's
        # outer ownership boundary closes provider and executable FDs.
        for plan in tuple(adapter._plans):
            plan.close()
        adapter._plans.clear()


def execute(
    request: dict,
    adapter: TerraformAdapter,
    *,
    guest,
    known_hosts: Path,
    environment=None,
    selected_host=None,
):
    """Own and close every provider capability on all validation and plan paths."""
    try:
        return _execute(
            request,
            adapter,
            guest=guest,
            known_hosts=known_hosts,
            environment=environment,
            selected_host=selected_host,
        )
    finally:
        adapter.close()
