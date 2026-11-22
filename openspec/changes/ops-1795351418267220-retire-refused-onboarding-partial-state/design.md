## Context

`disposable_promotion.finalize` writes, in order, `authority`, `liveness_config` and (non-CI cohorts) `executor_manifest`, then calls the installer, which creates the registry, pending registry and binding. A refusal before or inside the installer leaves a prefix of the first three. Unbound retirement required every output absent.

## Goals / Non-Goals

- Goal: the 2026-11-22 shape retires through `make retire-unbound-staging-client` and `make retire-unbound-staging-executor` without hand edits.
- Goal: refuse any state the intent could not have produced, and anything the installer writes.
- Non-goal: recompute `scope_sha256`. It binds the deploy controller's prepared intent (SOPS snapshot identity and input digests), which retirement does not have. The authority shape is checked; the liveness config binds its epoch.
- Non-goal: delete or move the partial outputs. They are not authority without a binding or registry, and a later finalization with the same scope cannot match once the client is gone from the ciphertext.

## Decisions

- Check in `_validate_inputs`, so both retirement verbs and the executor's preflight see the same request. Rejected: a separate verb or flag, which adds an operator path for one input shape.
- Add `partial_onboarding_sha256` to the request only when outputs exist. Clean-run requests and their existing journals and receipts stay byte-identical.
- When the manifest copy is present, refuse a non-retiring profile lifecycle record. `bind_executor` writes the assignment record before the binding file, so an installer crash between them leaves no output that shows the assignment; without this check the client would retire and executor retirement would then refuse. The read is lock-free because retirement holds the SOPS project lock that finalization holds while binding, and the executor's own preflight holds the profile lock.
- Compare the liveness config and manifest copy as bytes against what finalization writes (canonical JSON of the intent liveness with the authority epoch; the input manifest bytes). Rejected: semantic comparison, which would accept re-encoded content.

## Contracts and ownership

- Script: `scripts/retire-unbound-staging-client.py`; tests in `tests/unit/test_retire_unbound_staging_client.py`.
- Journal/receipt schema stays `schema_version: 1`; the request gains an optional key.

## Risks / Trade-offs

- Finalization write order changes → the prefix check refuses the new shape (fail-closed); `PARTIAL_ONBOARDING` cites the finalizer.
- Operator changes or removes a partial output mid-retirement → resume refuses (`retirement-bound`, or `retirement-journal` when only the last output is removed); the runbook says to keep them until both retirements finish.
- An authority-only state does not bind its epoch to this run; the liveness config does when present. Bounding `applied_at` by the absence window is a possible follow-up.

## Migration Plan

No migration. Rollback is a revert; a journal with the new key then refuses (fail-closed). The 2026-11-22 run is already cleaned up by hand and needs no action.
