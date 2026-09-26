#!/usr/bin/env python3
"""Explicit, policy-preserving SSH ownership migration for one pinned node."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

import fleet_inspection
from sshd_bundle_source import bundle_manifest
from sshd_contexts import bind_contexts


ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"schema_version", "mode", "inventory_alias", "inventory_path",
          "known_hosts_path", "contexts_path", "source_revision", "deployable_digest"}
HEX = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class OwnershipControllerError(ValueError):
    """Categorical failure; never expose private paths, addresses or receipts."""


def _module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-key")
        result[key] = value
    return result


def _document(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
        if (not isinstance(value, dict) or set(value) != FIELDS
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or not isinstance(value["mode"], str) or value["mode"] not in {"check", "deploy"}
                or not isinstance(value["inventory_alias"], str)
                or fleet_inspection.SAFE_NAME.fullmatch(value["inventory_alias"]) is None
                or any(not isinstance(value[key], str) or not Path(value[key]).is_absolute()
                       for key in ("inventory_path", "known_hosts_path", "contexts_path"))
                or not isinstance(value["source_revision"], str)
                or REVISION.fullmatch(value["source_revision"]) is None
                or not isinstance(value["deployable_digest"], str)
                or HEX.fullmatch(value["deployable_digest"]) is None):
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise OwnershipControllerError("configuration-invalid") from None


def _contexts(raw, alias):
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
        if not isinstance(value, dict) or set(value) != {alias}:
            raise ValueError
        return value[alias]
    except (TypeError, ValueError, UnicodeError):
        raise OwnershipControllerError("contexts-invalid") from None


def _transport_status(controller, host, pin, environment, identity, status):
    for transport in controller._transports(host):
        observed = controller.transaction_rpc(transport, pin, "status", None, environment)
        controller._same_identity(observed, identity, status)
        controller.fresh_sftp(transport, pin, environment)


def execute(config_path, *, controller=None):
    deploy = _module("deploy-controller")
    controller = controller or _module("sshd-baseline-controller")
    config = _document(deploy.read_input(config_path, private=True, exact_mode=0o600, limit=8192))
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE")
                   if key in os.environ}
    source = deploy.source_identity(ROOT, environment, require_clean=config["mode"] == "deploy")
    if (source["DEPLOY_SOURCE_REVISION"] != config["source_revision"]
            or source["DEPLOYABLE_SOURCE_DIGEST"] != config["deployable_digest"]):
        raise OwnershipControllerError("source-changed")
    inventory, inventory_fence = deploy.read_fenced_input(config["inventory_path"])
    pin, pin_fence = deploy.read_fenced_input(config["known_hosts_path"])
    contexts_raw, contexts_fence = deploy.read_fenced_input(
        config["contexts_path"], private=True, exact_mode=0o600, limit=32768)
    contexts = _contexts(contexts_raw, config["inventory_alias"])
    generation, _ = bundle_manifest()
    with tempfile.TemporaryDirectory(prefix=".vpn-ssh-ownership-", dir=Path.home()) as directory:
        directory = Path(directory)
        inventory_path = deploy.private_file(directory / "inventory.ini", inventory)
        pin_path = deploy.private_file(directory / "known_hosts", pin)
        host = fleet_inspection.select_hosts(inventory_path, [config["inventory_alias"]])[0]
        bind_contexts(contexts, host["address"], host["transport"], host["port"])
        for fence in (inventory_fence, pin_fence, contexts_fence):
            deploy.verify_input_fence(fence)
        prepare = {"intent": "sshd-ownership", "contexts": contexts, "timeout": 180,
                   "check_mode": config["mode"] == "check", "bundle_generation": generation}
        receipt = controller.transaction_rpc(host, pin_path, "prepare", prepare, environment)
        if config["mode"] == "check":
            if (set(receipt) != {"status", "snapshot_digest"}
                    or receipt["status"] not in {"unchanged", "would-change"}
                    or HEX.fullmatch(receipt["snapshot_digest"]) is None):
                raise OwnershipControllerError("receipt-invalid")
            return {"status": receipt["status"]}
        if receipt == {"status": "unchanged"}:
            return receipt
        identity = controller._identity(receipt)
        controller._same_identity(receipt, identity, "prepared")
        try:
            applied = controller.transaction_rpc(host, pin_path, "apply", {
                "generation": identity["generation"], "nonce": identity["nonce"]}, environment)
            controller._same_identity(applied, identity, "applied")
            _transport_status(controller, host, pin_path, environment, identity, "applied")
            current = controller.transaction_rpc(host, pin_path, "status", None, environment)
            controller._same_identity(current, identity, "applied")
            confirmed = controller.transaction_rpc(host, pin_path, "confirm", identity, environment)
            controller._same_identity(confirmed, identity, "committed")
        except BaseException:
            try:
                rolled = controller.transaction_rpc(host, pin_path, "rollback", {
                    "generation": identity["generation"], "nonce": identity["nonce"]}, environment,
                    cleanup=True)
                controller._same_identity(rolled, identity, "rolled_back")
            except BaseException:
                raise OwnershipControllerError("rollback-uncertain-recovery-armed") from None
            raise
        final = controller.transaction_rpc(host, pin_path, "status", None, environment)
        controller._same_identity(final, identity, "committed")
        return {"status": "committed"}


def main():
    try:
        result = execute(os.environ["SSH_OWNERSHIP_CONFIG"])
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "error", "reason": "ssh-ownership-migration-failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
