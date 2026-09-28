#!/usr/bin/env python3
"""Exact-node SSH baseline transaction controller.

The Ansible role renders desired policy; this controller owns the durable
prepare/apply/confirm/rollback lifecycle and fresh transport proofs.  It never
installs recovery, changes provider state, or accepts an arbitrary command.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from uuid import UUID

import fleet_inspection
from bootstrap_readiness import ReadinessError, run_command
from sshd_contexts import ContextError, bind_contexts, validate_contexts
from sshd_transaction_limits import (PROMOTION_PROOF_TIMEOUT_SECONDS, RPC_TIMEOUT_SECONDS,
                                     SFTP_TIMEOUT_SECONDS, TRANSACTION_TIMEOUT_SECONDS)


ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = "/usr/local/lib/vpn-sshd/sshd_bundle.py"
MAX_REQUEST = 32768
HEX = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
FAILURE_REASONS = {
    "apply-rpc-failed",
    "confirm-rpc-failed",
    "controller-failure",
    "fresh-sftp-failed",
    "management-transport-required",
    "onboarding-refused",
    "promotion-proof-failed",
    "promotion-proof-mismatch",
    "prepare-rpc-failed",
    "rollback-uncertain-recovery-armed",
    "transaction-identity-mismatch",
    "transaction-receipt-invalid",
    "status-rpc-failed",
}
REQUEST_FIELDS = {
    "schema_version", "mode", "inventory_alias", "inventory_path", "known_hosts_path",
    "contexts", "hardening_b64", "bundle_generation", "timeout_seconds",
    "promotion_config_path", "failure_receipt_path", "failure_receipt_parent_identity",
    "target_identity",
}
UNVALIDATED_FAILURE_SINK = object()


class BaselineError(Exception):
    """Categorical only; never include paths, addresses, output or nonces."""


class _PrepareOutcomeUnknown(BaseException):
    """Preserve an operator interruption after prepare may have armed state."""

    def __init__(self, interruption):
        super().__init__()
        self.interruption = interruption


def _is_hex(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def validate_request(value, failure_sink=UNVALIDATED_FAILURE_SINK):
    try:
        if not isinstance(value, dict) or set(value) != REQUEST_FIELDS or value["schema_version"] != 2:
            raise ValueError
        if value["mode"] not in {"deploy", "check"} or NAME.fullmatch(value["inventory_alias"]) is None:
            raise ValueError
        if any(not isinstance(value[key], str) or not value[key] for key in
               ("inventory_path", "known_hosts_path", "hardening_b64", "bundle_generation")):
            raise ValueError
        if not _is_hex(value["bundle_generation"]):
            raise ValueError
        if (type(value["timeout_seconds"]) is not int
                or not 60 <= value["timeout_seconds"] <= TRANSACTION_TIMEOUT_SECONDS):
            raise ValueError
        validate_contexts(value["contexts"])
        hardening = base64.b64decode(value["hardening_b64"], validate=True)
        if not 0 < len(hardening) <= 8192 or base64.b64encode(hardening).decode() != value["hardening_b64"]:
            raise ValueError
        target = value["target_identity"]
        if (not isinstance(target, dict)
                or set(target) != {"inventory_alias", "public_service_address_sha256", "deployable_digest"}
                or target["inventory_alias"] != value["inventory_alias"]
                or any(not _is_hex(target[key])
                       for key in ("public_service_address_sha256", "deployable_digest"))):
            raise ValueError
        if value["mode"] == "deploy":
            if not isinstance(value["promotion_config_path"], str) or not value["promotion_config_path"]:
                raise ValueError
            if failure_sink is UNVALIDATED_FAILURE_SINK:
                failure_sink = _failure_sink(
                    value["failure_receipt_path"], value["failure_receipt_parent_identity"]
                )
            elif failure_sink is None:
                raise ValueError
        elif (value["promotion_config_path"] is not None
              or value["failure_receipt_path"] is not None
              or value["failure_receipt_parent_identity"] is not None):
            raise ValueError
        else:
            failure_sink = None
        return value | {"hardening": hardening, "failure_sink": failure_sink}
    except (ValueError, TypeError, KeyError, BaselineError, ContextError):
        raise BaselineError("request-invalid") from None


def _prevalidated_failure_sink(value):
    if (not isinstance(value, dict) or value.get("schema_version") != 2
            or value.get("mode") != "deploy"):
        return None
    try:
        return _failure_sink(
            value.get("failure_receipt_path"), value.get("failure_receipt_parent_identity")
        )
    except BaselineError:
        return None


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _failure_sink(value, expected_identity):
    if (not isinstance(value, str) or not Path(value).is_absolute()
            or str(Path(value)) != value or any(part in (".", "..") for part in Path(value).parts)
            or any(ord(char) < 32 or ord(char) == 127
                   or 0xD800 <= ord(char) <= 0xDFFF for char in value)
            or not isinstance(expected_identity, dict)
            or set(expected_identity) != {"device", "inode"}
            or any(type(expected_identity[key]) is not int or expected_identity[key] < 0
                   for key in expected_identity)):
        raise BaselineError("request-invalid")
    path = Path(value)
    try:
        if os.path.lexists(path):
            raise BaselineError("request-invalid")
        parent = path.parent
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or {"device": info.st_dev, "inode": info.st_ino} != expected_identity):
            raise BaselineError("request-invalid")
        for ancestor in parent.parents:
            current = ancestor.lstat()
            sticky_root = current.st_uid == 0 and current.st_mode & stat.S_ISVTX
            if (not stat.S_ISDIR(current.st_mode)
                    or current.st_uid not in (0, os.geteuid())
                    or (current.st_mode & 0o022 and not sticky_root)):
                raise BaselineError("request-invalid")
        return path, (info.st_dev, info.st_ino)
    except BaselineError:
        raise
    except (OSError, UnicodeError):
        raise BaselineError("request-invalid") from None


def _publish_failure(sink, reason):
    if reason not in FAILURE_REASONS:
        raise OSError("failure receipt reason invalid")
    path, parent_identity = sink
    payload = _json({"schema_version": 1, "status": "failed", "reason": reason}) + b"\n"
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".sshd-baseline-failure-" + secrets.token_hex(16)
    created = False
    try:
        info = os.fstat(parent)
        if ((info.st_dev, info.st_ino) != parent_identity or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise OSError("failure receipt parent changed")
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
        created = True
        try:
            os.fchmod(handle, 0o600)
            view = memoryview(payload)
            while view:
                written = os.write(handle, view)
                if written <= 0:
                    raise OSError("failure receipt write incomplete")
                view = view[written:]
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.unlink(temporary, dir_fd=parent)
        created = False
        os.fsync(parent)
    finally:
        if created:
            try:
                os.unlink(temporary, dir_fd=parent)
                os.fsync(parent)
            except OSError:
                # Best-effort cleanup must not replace the publication error.
                pass
        os.close(parent)


def _fixed_command(host, known_hosts, action):
    command = fleet_inspection.ssh_command(host, known_hosts)
    command[-1] = "sudo -n /usr/bin/python3 -I -B " + DISPATCHER + " " + action
    return command


def transaction_rpc(host, known_hosts, action, request, environment, *, cleanup=False):
    reason = (action + "-rpc-failed"
              if action in {"prepare", "apply", "status", "confirm", "rollback"}
              else "controller-failure")
    status, output = run_command(
        _fixed_command(host, known_hosts, action), timeout=RPC_TIMEOUT_SECONDS, environment=environment,
        capture=True, input_data=None if request is None else _json(request), defer_cancellation=cleanup,
    )
    if status or len(output) > 16384:
        raise BaselineError(reason)
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        raise BaselineError(reason) from None
    if not isinstance(result, dict) or result.get("status") == "error":
        raise BaselineError(reason)
    return result


def fresh_sftp(host, known_hosts, environment):
    status, _ = run_command(fleet_inspection.sftp_command(host, known_hosts), timeout=SFTP_TIMEOUT_SECONDS,
                            environment=environment, input_data=b"pwd\nquit\n")
    if status:
        raise BaselineError("fresh-sftp-failed")


def promotion_proof(root, config, environment):
    status, output = run_command([sys.executable, str(root / "scripts/sshd-promotion-proof.py"),
                                  "--config", str(config)], timeout=PROMOTION_PROOF_TIMEOUT_SECONDS,
                                 capture=True, environment=environment)
    if status or len(output) > 16384:
        raise BaselineError("promotion-proof-failed")
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        raise BaselineError("promotion-proof-failed") from None
    fields = {"schema_version", "status", "target_identity", "observed_at"}
    identity_fields = {"inventory_alias", "public_service_address_sha256", "deployable_digest"}
    identity = result.get("target_identity") if isinstance(result, dict) else None
    if (not isinstance(result, dict) or set(result) != fields
            or result["schema_version"] != 1 or result["status"] != "passed"
            or type(result["observed_at"]) is not int or result["observed_at"] < 0
            or not isinstance(identity, dict) or set(identity) != identity_fields
            or not isinstance(identity["inventory_alias"], str)
            or not _is_hex(identity["public_service_address_sha256"])
            or not _is_hex(identity["deployable_digest"])):
        raise BaselineError("promotion-proof-failed")
    return result


def _rollback_capability(receipt):
    if (not isinstance(receipt, dict) or not isinstance(receipt.get("generation"), str)
            or not _is_hex(receipt.get("nonce"))):
        raise BaselineError("transaction-receipt-invalid")
    try:
        if str(UUID(receipt["generation"])) != receipt["generation"]:
            raise ValueError
    except ValueError:
        raise BaselineError("transaction-receipt-invalid") from None
    return {key: receipt[key] for key in ("generation", "nonce")}


def _identity(receipt):
    fields = {"generation", "nonce", "status", "deadline", "snapshot_digest"}
    capability = _rollback_capability(receipt)
    if (set(receipt) != fields or not _is_hex(receipt["snapshot_digest"])
            or type(receipt["deadline"]) is not int):
        raise BaselineError("transaction-receipt-invalid")
    return capability | {"snapshot_digest": receipt["snapshot_digest"]}


def _same_identity(receipt, identity, status):
    if (not isinstance(receipt, dict) or receipt.get("status") != status
            or any(receipt.get(key) != value for key, value in identity.items())):
        raise BaselineError("transaction-identity-mismatch")


def _transports(host):
    public = dict(host, transport=host["address"])
    result = [public]
    if (host["transport"].lower(), host["port"]) != (host["address"].lower(), host["port"]):
        result.append(host)
    return result


def prepare_promotion(path, environment):
    """Only a typed staging intent can invoke the fixed onboarding adapter."""
    try:
        with os.fdopen(fleet_inspection._open_local_file(path, private=True), "rb") as handle:
            raw = handle.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError
        document = json.loads(raw)
        if isinstance(document, dict) and document.get("kind") == "disposable-staging-intent":
            from disposable_promotion import finalize
            return finalize(document, environment), True
        return path, False
    except (OSError, ValueError, fleet_inspection.InspectionError):
        raise BaselineError("onboarding-refused") from None


def _execute_validated(value, environment, *, rpc, sftp, proof, clock, onboard):
    hosts = fleet_inspection.select_hosts(Path(value["inventory_path"]), [value["inventory_alias"]])
    host = hosts[0]
    try:
        bind_contexts(value["contexts"], host["address"], host["transport"], host["port"])
    except ContextError:
        raise BaselineError("management-transport-required") from None
    known_hosts = Path(value["known_hosts_path"])
    if value["mode"] == "deploy":
        config, first_onboarding = onboard(Path(value["promotion_config_path"]), environment)
        value["promotion_config_path"] = str(config)
        if first_onboarding:
            started = int(clock())
            observed = proof(ROOT, config, environment)
            if (observed.get("target_identity") != value["target_identity"]
                    or type(observed.get("observed_at")) is not int
                    or observed["observed_at"] < started):
                raise BaselineError("promotion-proof-mismatch")
    prepare = {"intent": "sshd-baseline", "contexts": value["contexts"],
               "hardening_b64": value["hardening_b64"], "timeout": value["timeout_seconds"],
               "check_mode": value["mode"] == "check", "bundle_generation": value["bundle_generation"]}
    if value["mode"] == "check":
        receipt = rpc(host, known_hosts, "prepare", prepare, environment)
        if (not isinstance(receipt, dict)
                or set(receipt) != {"status", "snapshot_digest"}
                or receipt["status"] not in {"unchanged", "would-change"}
                or not _is_hex(receipt["snapshot_digest"])):
            raise BaselineError("transaction-receipt-invalid")
        return {"status": receipt["status"]}
    try:
        receipt = rpc(host, known_hosts, "prepare", prepare, environment)
    except (KeyboardInterrupt, SystemExit) as error:
        raise _PrepareOutcomeUnknown(error) from None
    except BaseException:
        raise BaselineError("rollback-uncertain-recovery-armed") from None
    if receipt == {"status": "unchanged"}:
        return receipt
    rollback_capability = None
    identity = None
    rollback_needed = True
    try:
        rollback_capability = _rollback_capability(receipt)
        identity = _identity(receipt)
        _same_identity(receipt, identity, "prepared")
        applied = rpc(host, known_hosts, "apply", {"generation": identity["generation"],
                      "nonce": identity["nonce"]}, environment)
        _same_identity(applied, identity, "applied")
        applied_after = int(clock()) + 1
        for transport in _transports(host):
            status = rpc(transport, known_hosts, "status", None, environment)
            _same_identity(status, identity, "applied")
            sftp(transport, known_hosts, environment)
        observed = proof(ROOT, Path(value["promotion_config_path"]), environment)
        if (observed.get("target_identity") != value["target_identity"]
                or type(observed.get("observed_at")) is not int or observed["observed_at"] < applied_after):
            raise BaselineError("promotion-proof-mismatch")
        final_status = rpc(host, known_hosts, "status", None, environment)
        _same_identity(final_status, identity, "applied")
        confirmed = rpc(host, known_hosts, "confirm", {"generation": identity["generation"],
                        "nonce": identity["nonce"], "snapshot_digest": identity["snapshot_digest"]}, environment)
        _same_identity(confirmed, identity, "committed")
        rollback_needed = False
        post = rpc(host, known_hosts, "status", None, environment)
        _same_identity(post, identity, "committed")
        return {"status": "committed"}
    except BaseException:
        if rollback_needed:
            if rollback_capability is None:
                raise BaselineError("rollback-uncertain-recovery-armed") from None
            try:
                rolled = rpc(host, known_hosts, "rollback", rollback_capability,
                             environment, cleanup=True)
                rolled_identity = _identity(rolled)
                _same_identity(rolled, rolled_identity, "rolled_back")
                expected = identity if identity is not None else rollback_capability
                if any(rolled_identity.get(key) != expected_value
                       for key, expected_value in expected.items()):
                    raise BaselineError("transaction-identity-mismatch")
            except BaseException:
                raise BaselineError("rollback-uncertain-recovery-armed") from None
        raise


def execute(request, environment, *, rpc=transaction_rpc, sftp=fresh_sftp, proof=promotion_proof,
            clock=time.time, onboard=prepare_promotion):
    failure_sink = _prevalidated_failure_sink(request)
    try:
        value = validate_request(request, failure_sink)
        return _execute_validated(
            value, environment, rpc=rpc, sftp=sftp, proof=proof, clock=clock, onboard=onboard,
        )
    except (BaselineError, ReadinessError, fleet_inspection.InspectionError, OSError, ValueError,
            KeyboardInterrupt, SystemExit, _PrepareOutcomeUnknown) as error:
        if failure_sink is not None:
            reason = ("rollback-uncertain-recovery-armed"
                      if isinstance(error, _PrepareOutcomeUnknown) else str(error)
                      if isinstance(error, BaselineError) and str(error) in FAILURE_REASONS
                      else "controller-failure")
            try:
                _publish_failure(failure_sink, reason)
            except (OSError, UnicodeError):
                # Preserve the original controller failure when the private receipt cannot be published.
                pass
        if isinstance(error, _PrepareOutcomeUnknown):
            raise error.interruption from None
        raise


def _request():
    data = sys.stdin.buffer.read(MAX_REQUEST + 1)
    if not data or len(data) > MAX_REQUEST:
        raise BaselineError("request-invalid")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError):
        raise BaselineError("request-invalid") from None


def main():
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE")
                   if key in os.environ}
    try:
        result = execute(_request(), environment)
        print(json.dumps(result, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"status": "error", "reason": "ssh-baseline-transaction-failed"}))
        return 130
    except SystemExit as error:
        print(json.dumps({"status": "error", "reason": "ssh-baseline-transaction-failed"}))
        return error.code if type(error.code) is int and error.code != 0 else 1
    except (BaselineError, ReadinessError, fleet_inspection.InspectionError, OSError, ValueError):
        print(json.dumps({"status": "error", "reason": "ssh-baseline-transaction-failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
