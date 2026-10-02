#!/usr/bin/env python3
"""Retire a prepared VM only after its exact unbound client was retired."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import disposable_liveness_executor as executor

ROOT = Path(__file__).resolve().parents[1]


def _client_module():
    spec = importlib.util.spec_from_file_location(
        "unbound_client_retirement", ROOT / "scripts/retire-unbound-staging-client.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _retired_client(module, paths, runner):
    intent, base = module._validate_inputs(paths)
    journal, _ = module._read_json(paths["journal_path"], "client retirement journal")
    request = journal.get("request")
    if (
        not isinstance(request, dict)
        or set(request) != {*base, "ciphertext_before_sha256"}
        or {key: request.get(key) for key in base} != base
        or journal.get("state") != "verified"
    ):
        raise module.RetirementError("retirement-executor-client")
    module._validate_journal(journal, request)
    receipt, payload = module._read_json(
        paths["receipt_path"], "client retirement receipt"
    )
    if receipt != module._receipt(request, journal["candidate"]):
        raise module.RetirementError("retirement-executor-client")
    if (
        module._candidate_state(
            paths["sops_file"],
            request["ciphertext_before_sha256"],
            journal["candidate"],
        )
        != "after"
    ):
        raise module.RetirementError("retirement-executor-client")
    document = module._decrypt(paths["sops_file"], runner)
    if executor._client_secret_paths(
        document, intent["client"]
    ) or module._xray_cohort_references(document, intent["client"]):
        raise module.RetirementError("retirement-executor-client")
    return intent, base, payload, journal


def retire_executor(
    *,
    intent_path: Path,
    cleanup_manifest_path: Path,
    absence_evidence_path: Path,
    state_path: Path,
    sops_file: Path,
    journal_path: Path,
    receipt_path: Path,
    executor_receipt_path: Path,
    home: Path,
    runner,
) -> dict:
    module = _client_module()
    paths = {
        "intent_path": intent_path.absolute(),
        "cleanup_manifest_path": cleanup_manifest_path.absolute(),
        "absence_evidence_path": absence_evidence_path.absolute(),
        "state_path": state_path.absolute(),
        "sops_file": sops_file.absolute(),
        "journal_path": journal_path.absolute(),
        "receipt_path": receipt_path.absolute(),
    }
    executor_receipt_path = executor_receipt_path.absolute()
    if len(set(paths.values()) | {executor_receipt_path}) != len(paths) + 1:
        raise module.RetirementError("retirement-input")
    parent, _ = module._parent_fd(executor_receipt_path, "executor receipt")
    try:
        info = os.fstat(parent)
        sink_identity = info.st_dev, info.st_ino
    finally:
        os.close(parent)
    manifest, _ = module._read_json(paths["cleanup_manifest_path"], "cleanup manifest")
    guard = module._guard()
    try:
        with guard.lifecycle.locked(manifest) as authority:
            authority.current(paths["cleanup_manifest_path"], manifest)
            intent, _ = module._validate_inputs(paths)
            if executor_receipt_path in {
                Path(path)
                for path in (*intent["inputs"].values(), *intent["outputs"].values())
            }:
                raise module.RetirementError("retirement-input")
            with module._locks(module.lock_paths(paths["sops_file"], intent["client"])):
                intent, base, receipt, client_journal = _retired_client(
                    module, paths, runner
                )

                def preflight():
                    if module._validate_inputs(paths)[1] != base:
                        raise module.RetirementError("retirement-input")
                    if (
                        module._read_json(
                            paths["receipt_path"], "client retirement receipt"
                        )[1]
                        != receipt
                        or module._read_json(
                            paths["journal_path"], "client retirement journal"
                        )[0]
                        != client_journal
                        or module._candidate_state(
                            paths["sops_file"],
                            client_journal["request"]["ciphertext_before_sha256"],
                            client_journal["candidate"],
                        )
                        != "after"
                    ):
                        raise module.RetirementError("retirement-executor-client")
                    parent, _ = module._parent_fd(
                        executor_receipt_path, "executor receipt"
                    )
                    try:
                        info = os.fstat(parent)
                        if (info.st_dev, info.st_ino) != sink_identity:
                            raise module.RetirementError("retirement-input")
                    finally:
                        os.close(parent)

                result = executor.retire_prepared_executor(
                    Path(intent["inputs"]["executor_manifest"]),
                    executor_receipt_path,
                    client_receipt_sha256=hashlib.sha256(receipt).hexdigest(),
                    home=home,
                    runner=runner,
                    preflight=preflight,
                )
    except (guard.GuardError, executor.ExecutorError) as exc:
        raise module.RetirementError("retirement-executor") from exc
    try:
        runner(
            (
                str(ROOT / "scripts/audit-log.sh"),
                "append-best-effort",
                "--action",
                "retire-unbound-staging-executor",
                "--note",
                "executor-retired",
            ),
            timeout=30,
        )
    except Exception:
        print("retire-unbound-staging-executor: audit-unavailable", file=sys.stderr)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "intent",
        "cleanup-manifest",
        "absence-evidence",
        "state",
        "sops-file",
        "journal",
        "receipt",
        "executor-receipt",
    ):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        result = retire_executor(
            intent_path=args.intent,
            cleanup_manifest_path=args.cleanup_manifest,
            absence_evidence_path=args.absence_evidence,
            state_path=args.state,
            sops_file=args.sops_file,
            journal_path=args.journal,
            receipt_path=args.receipt,
            executor_receipt_path=args.executor_receipt,
            home=Path.home(),
            runner=executor._run_command,
        )
        print(
            json.dumps(
                {key: result[key] for key in ("schema_version", "status", "changed")},
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        print("retire-unbound-staging-executor: retirement-refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
