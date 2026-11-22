# TFR-1795357890236562: Read OpenTofu state through the encrypted backend in every script

## Objective

No script reads, copies or binds a local OpenTofu state file; every state read is an in-memory `state pull` that fails closed, and the disposable CI deploy keeps its state in a per-run encrypted local backend.

## Ownership

New `scripts/tofu_state.py`; state readers in `scripts/` (recovery, cloud promotion, observability cleanup, staging cleanup guards, unbound retirement, tailnet bootstrap and promotion, CI deploy and seed cleanup, permission audit); `Makefile` staging cleanup and retirement targets; their unit tests; `docs/how-to/deploy.md`, `docs/how-to/ci-real-deploy.md` and the folder notes that describe state.

## Execution

- [x] TFR-1795358620771976 Add the in-memory state pull helper and move the recovery and cloud promotion readers onto it #feature !high @item:TFR-1795357890236562
- [x] TFR-1795358638408897 Move the observability cleanup, CI seed cleanup and permission audit off local state paths #feature !high @item:TFR-1795357890236562
- [x] TFR-1795358658062021 Give the disposable CI deploy a per-run encrypted local backend #feature !high @item:TFR-1795357890236562
- [x] TFR-1795358675141561 Move the staging cleanup guards, unbound retirement and tailnet bootstrap onto state pull #feature !high @item:TFR-1795357890236562
- [x] TFR-1795358692563336 Move the tailnet network promotion and controller onto state pull with the state identity #feature !high @item:TFR-1795357890236562

## Verification

Local: the unit test files of every changed script, `make check`. Remote CI: PR checks. Live: not in this change; the next authorized staging cleanup and label-gated CI deploy exercise the pulled state.
