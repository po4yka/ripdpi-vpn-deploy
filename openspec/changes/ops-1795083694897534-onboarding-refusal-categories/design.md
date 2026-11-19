## Context

See proposal.md. Four layers collapse categories: `client_payload.main()` allow-lists only some `ValueError` texts; `install_liveness_sentinel._run` discards child stderr; `recovery_promotion.finalize` catches every inner error; `sshd-baseline-controller.prepare_promotion` catches every `ValueError`, which includes `PromotionError`.

## Goals / Non-Goals

- Goal: the missing-workspace case reports `recovery-promotion-payload-input-unavailable` in the baseline failure receipt.
- Goal: each layer still maps unknown failures to its generic category.
- Non-goal: surfacing every installer category (62 fixed strings) in the receipt. Only the emitter's payload input categories cross finalization.
- Non-goal: changing the disposable staging promotion path (`disposable_promotion.finalize`), which keeps `onboarding-refused`.

## Decisions

- `bounded_command` gains an optional `refusals` mapping from the complete stderr bytes to a fixed category. Only an exact match changes the category; partial or other stderr stays private and gives `command-failed`. Rejected: returning stderr to callers, which would let child text reach diagnostics.
- The installer owns `EMITTER_REFUSALS` and passes it only to the `emit-singbox.sh` call. `command-failed` keeps its retry meaning for receipt polling because other calls never receive refusals.
- Finalization re-raises its own `PromotionError` and prefixes the two emitter categories; the prefix keeps one naming family for receipt reasons.
- The baseline controller lists `PROMOTION_REASONS` literally and adds them to `FAILURE_REASONS`, so the receipt stays a fixed enum checked before publication. Rejected: a regex over category text, which would not be a fixed set.

## Contracts and ownership

- Scripts only: `scripts/client_payload.py`, `scripts/fleet_inspection.py`, `scripts/install_liveness_sentinel.py`, `scripts/recovery_promotion.py`, `scripts/sshd-baseline-controller.py`; operator doc row in `docs/how-to/deploy.md`.
- The receipt schema keeps `schema_version: 1`, `status: failed`, `reason`; the reason enum grows. No programmatic consumer reads the reason.

## Risks / Trade-offs

- A new finalization category can be missed in `PROMOTION_REASONS` → it reports `onboarding-refused`, the previous behavior; a controller test pins an unlisted category to that fallback.
- Emitter text changes break the exact-match mapping → the installer reports `command-failed`; the emitter and installer tests pin both sides.

## Migration Plan

No migration. Rollback is a revert of the change; older receipts stay valid because `onboarding-refused` is still a reason. No live action is needed; the next deploy that refuses at onboarding publishes the specific reason.
