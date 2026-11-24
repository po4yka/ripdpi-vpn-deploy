# SCR-1795491503477936: Retire an expired never-assigned disposable liveness executor

## Objective

`make retire-expired-disposable-liveness EXECUTOR_MANIFEST=… EXECUTOR_RECEIPT=…` removes an expired prepared executor that was never assigned, through the existing profile journal and removal steps, so no leftover executor needs a direct `colima delete`.

## Ownership

`scripts/disposable_liveness_executor.py`, the `retire-expired-disposable-liveness` Make goal and its entries in the disposable liveness command-variable and export lists in `Makefile`, `tests/unit/test_disposable_liveness_executor.py`, `tests/unit/test_disposable_liveness_make.py`, `docs/reference/protocol-liveness.md`, generated `docs/reference/make-targets.md`.

## Execution

- [x] SCR-1795491794457312 Add the expired-executor retirement verb and Make goal #feature @item:SCR-1795491503477936
- [x] SCR-1795491812861576 Document expired-executor retirement in the protocol liveness reference #feature @item:SCR-1795491503477936
- [x] SCR-1795491829921909 Retire the leftover staging executors with the new goal #feature @item:SCR-1795491503477936

## Verification

- Local: `python3 -m pytest tests/unit/test_disposable_liveness_executor.py tests/unit/test_disposable_liveness_make.py tests/unit/test_retire_unbound_staging_client.py`, `make docs-check`.
- Remote CI: PR checks.
- Dry-run: not applicable (no deployed runtime change).
- Staging: the two leftover executors of the 2026-11-22/24 staging runs retire with the new goal; `colima list` no longer shows them.
- Live, client, artifact: not applicable.
