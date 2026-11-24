# Change: Retire an expired never-assigned disposable liveness executor

Task ID: `SCR-1795491503477936`

## Why

`make prepare-disposable-liveness` creates a one-shot Colima executor. It leaves the operator machine only through `deonboard-disposable-liveness` (assigned executors) or `retire-unbound-staging-executor`, which needs a verified client retirement receipt from a promotion intent that names the executor. The 2026-11-22/24 staging runs left two executors outside both paths: one was prepared for a continuation and no intent names it, and the other is named only by an intent whose run had already retired its client through de-onboarding, so the client step refuses with `retirement-secrets`. Both VMs kept running, and the only way out was a direct `colima delete` that skips the profile journal.

## What Changes

- New Make goal `retire-expired-disposable-liveness` with exactly the command-line fields `EXECUTOR_MANIFEST` and `EXECUTOR_RECEIPT`, inside the existing disposable liveness command-variable boundary and machine build gate.
- New `retire-expired` verb in `scripts/disposable_liveness_executor.py`. It reuses the existing prepared-executor removal primitive; with no client receipt, the authority is the manifest's expiry, checked under the profile lease.
- The receipt status is `retired-expired` and carries no client field. The existing unbound path and its `retired-prepared` receipt are unchanged.

## Capabilities

### New Capabilities

- `operations/disposable-liveness-expired-retirement`: supported removal of an expired, never-assigned disposable liveness executor.

### Modified Capabilities

- None.

## Impact

- `scripts/disposable_liveness_executor.py`, the Makefile goal, its command-variable list and export list, `tests/unit/test_disposable_liveness_executor.py`, `tests/unit/test_disposable_liveness_make.py`, `docs/reference/protocol-liveness.md` and the generated `docs/reference/make-targets.md`.
- Operator machine only. No Terraform, Ansible, secrets schema, client contract or deployed node changes.
