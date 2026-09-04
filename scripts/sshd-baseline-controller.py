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


class BaselineError(Exception):
    """Categorical only; never include paths, addresses, output or nonces."""


def validate_request(value):
    fields = {"schema_version", "mode", "inventory_alias", "inventory_path", "known_hosts_path",
              "contexts", "hardening_b64", "bundle_generation", "timeout_seconds",
              "promotion_config_path", "target_identity"}
    try:
        if not isinstance(value, dict) or set(value) != fields or value["schema_version"] != 1:
            raise ValueError
        if value["mode"] not in {"deploy", "check"} or NAME.fullmatch(value["inventory_alias"]) is None:
            raise ValueError
        if any(not isinstance(value[key], str) or not value[key] for key in
               ("inventory_path", "known_hosts_path", "hardening_b64", "bundle_generation")):
            raise ValueError
        if HEX.fullmatch(value["bundle_generation"]) is None:
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
                or any(HEX.fullmatch(target[key]) is None
                       for key in ("public_service_address_sha256", "deployable_digest"))):
            raise ValueError
        if value["mode"] == "deploy":
            if not isinstance(value["promotion_config_path"], str) or not value["promotion_config_path"]:
                raise ValueError
        elif value["promotion_config_path"] is not None:
            raise ValueError
        return value | {"hardening": hardening}
    except (ValueError, TypeError, KeyError, BaselineError, ContextError):
        raise BaselineError("request-invalid") from None


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fixed_command(host, known_hosts, action):
    command = fleet_inspection.ssh_command(host, known_hosts)
    command[-1] = "sudo -n /usr/bin/python3 -I -B " + DISPATCHER + " " + action
    return command


def transaction_rpc(host, known_hosts, action, request, environment, *, cleanup=False):
    status, output = run_command(
        _fixed_command(host, known_hosts, action), timeout=RPC_TIMEOUT_SECONDS, environment=environment,
        capture=True, input_data=None if request is None else _json(request), defer_cancellation=cleanup,
    )
    if status or len(output) > 16384:
        raise BaselineError("transaction-rpc-failed")
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        raise BaselineError("transaction-rpc-failed") from None
    if not isinstance(result, dict) or result.get("status") == "error":
        raise BaselineError("transaction-rpc-failed")
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
            or HEX.fullmatch(identity["public_service_address_sha256"]) is None
            or HEX.fullmatch(identity["deployable_digest"]) is None):
        raise BaselineError("promotion-proof-failed")
    return result


def _identity(receipt):
    fields = {"generation", "nonce", "status", "deadline", "snapshot_digest"}
    if (not isinstance(receipt, dict) or set(receipt) != fields
            or not isinstance(receipt["generation"], str)
            or HEX.fullmatch(receipt["nonce"]) is None
            or HEX.fullmatch(receipt["snapshot_digest"]) is None
            or type(receipt["deadline"]) is not int):
        raise BaselineError("transaction-receipt-invalid")
    try:
        if str(UUID(receipt["generation"])) != receipt["generation"]:
            raise ValueError
    except ValueError:
        raise BaselineError("transaction-receipt-invalid") from None
    return {key: receipt[key] for key in ("generation", "nonce", "snapshot_digest")}


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


def execute(request, environment, *, rpc=transaction_rpc, sftp=fresh_sftp, proof=promotion_proof,
            clock=time.time, onboard=prepare_promotion):
    value = validate_request(request)
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
    receipt = rpc(host, known_hosts, "prepare", prepare, environment)
    if value["mode"] == "check":
        if (set(receipt) != {"status", "snapshot_digest"}
                or receipt["status"] not in {"unchanged", "would-change"}
                or HEX.fullmatch(receipt["snapshot_digest"]) is None):
            raise BaselineError("transaction-receipt-invalid")
        return {"status": receipt["status"]}
    if receipt == {"status": "unchanged"}:
        return receipt
    identity = _identity(receipt)
    _same_identity(receipt, identity, "prepared")
    rollback_needed = True
    try:
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
            try:
                rolled = rpc(host, known_hosts, "rollback", {"generation": identity["generation"],
                             "nonce": identity["nonce"]}, environment, cleanup=True)
                _same_identity(rolled, identity, "rolled_back")
            except BaseException:
                raise BaselineError("rollback-uncertain-recovery-armed") from None
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
    except (BaselineError, ReadinessError, fleet_inspection.InspectionError, OSError, ValueError):
        print(json.dumps({"status": "error", "reason": "ssh-baseline-transaction-failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
