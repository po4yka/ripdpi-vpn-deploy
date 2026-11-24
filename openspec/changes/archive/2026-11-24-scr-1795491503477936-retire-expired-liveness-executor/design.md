## Context

See proposal.md. `retire_prepared_executor` in `scripts/disposable_liveness_executor.py` already removes a prepared executor under its profile lease: it refuses an executor whose profile journal records an assignment (`executor-claimed`), verifies the marker, configuration and Docker context, journals the removal so that it can resume after stop or delete, and fences the profile name. Its only caller, `retire-unbound-staging-executor`, supplies a verified client retirement receipt as authority.

## Goals / Non-Goals

- Goal: a supported removal for an expired prepared executor that has no client receipt.
- Non-goal: removing an assigned executor; that stays with `deonboard-disposable-liveness`, which first proves provider absence and retires the client.
- Non-goal: removing an executor before its manifest expires.

## Decisions

- Expiry is the authority. `bind_executor` calls `load_live_executor`, which requires `created_at <= now < expires_at`, so an expired executor can never be assigned, and an unassigned one holds no client credentials (runtime provisioning reads none). Rejected: requiring provider-absence evidence of some run, because no artifact links an intent-less executor to a run, and that evidence would not prove anything about the executor.
- The expiry check runs inside the profile lease on the leased manifest bytes, so it cannot be raced by a concurrent bind.
- Reuse the primitive instead of a second removal routine: `client_receipt_sha256=None` plus `now` selects the expired mode. The request and receipt then omit the client field and the status is `retired-expired`, so the two authorities stay distinguishable in evidence.
- One Make goal with exactly two fields, inside the existing disposable liveness boundary (single goal, literal values, exported fields, build gate).

## Contracts and ownership

- Script: `scripts/disposable_liveness_executor.py` gains the `retire-expired` verb.
- Make: `retire-expired-disposable-liveness` with `EXECUTOR_MANIFEST` and `EXECUTOR_RECEIPT`.
- Docs: `docs/reference/protocol-liveness.md`, generated `docs/reference/make-targets.md`.

## Risks / Trade-offs

- An operator could retire an executor that a run still intended to use → only after expiry, when that run could no longer bind it anyway; the deploy would refuse in the same way.
- The receipt does not name a run → it names the executor manifest digest, which is the executor's identity; the operator keeps it beside the run's other evidence.

## Migration Plan

Additive. Rollback: revert the commit; leftover executors then need manual handling again. Gate: unit tests, `make docs-check`, then the two leftover executors retired with the command.
