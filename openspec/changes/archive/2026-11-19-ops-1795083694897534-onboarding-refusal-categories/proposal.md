# Change: Report specific onboarding refusal categories in SSH baseline failure receipts

Task ID: `OPS-1795083694897534`

## Why

A deploy failed because the client emitter could not read Terraform outputs in a fresh worktree without the initialized workspace data. The SSH baseline failure receipt said only `onboarding-refused`: the emitter, the liveness sentinel installer, recovery promotion finalization and the baseline controller each replaced the specific category with a generic one. The operator had no categorical clue to the cause.

## What Changes

- The client emitter reports `payload-input-unavailable` and `payload-deadline-exceeded` as themselves instead of `plaintext secrets unavailable` or `materialization refused`.
- The liveness sentinel installer maps exactly those emitter stderr lines to the same categories; every other command failure stays `command-failed`.
- Recovery and cloud promotion finalization keeps its own `recovery-promotion-*` categories and turns the two emitter categories into `recovery-promotion-payload-input-unavailable` and `recovery-promotion-payload-deadline-exceeded`; other failures stay `recovery-promotion-finalization-refused`.
- The SSH baseline failure receipt accepts a fixed set of `recovery-promotion-*` reasons in addition to the existing reasons. Unknown categories stay `onboarding-refused`. The receipt shape is unchanged; its reason enum grows.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `operations/deployment-recovery`: onboarding refusals in deploy mode report their fixed category in the private baseline failure receipt.

## Impact

- Scripts: `scripts/client_payload.py`, `scripts/fleet_inspection.py`, `scripts/install_liveness_sentinel.py`, `scripts/recovery_promotion.py`, `scripts/sshd-baseline-controller.py`.
- Contract: the baseline failure receipt reason enum (operator-read private file). No Terraform, Ansible, secrets or client payload change.
