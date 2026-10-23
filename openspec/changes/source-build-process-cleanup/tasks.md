# ANS-1792773060904443: Make source build process cleanup deterministic

## Objective

Confirm foreground build cleanup without false macOS failures or surviving descendants. Pass the full source gate and complete the dependency update task.

## Ownership

- Runtime worker owns `ansible/roles/runtime-release/files/runtime_build_receipt.py`, `tests/unit/test_runtime_build_receipt.py` and `ansible/roles/runtime-release/CLAUDE.md`.
- Test worker owns `tests/unit/test_monitor_reality_target.py`, `tests/unit/test_smoke_test_cleanup.py` and `tests/unit/test_transport_site_transaction.py`.
- The primary maintainer owns `tests/CLAUDE.md`, planning and portfolio files, the full gate, review and Git publication. Shared-file edits are serialized. Workers do not revert other work.

## Execution

- [ ] ANS-1792773632226275 Retain source build group identity through completion and cancellation with real regression coverage #bug !high @item:ANS-1792773060904443
- [ ] ANS-1792773633446824 Synchronize local process fixtures and preserve complete smoke and transaction checks #bug !high @item:ANS-1792773060904443
- [ ] ANS-1792773634640147 Pass full local and hosted gates and verify the source change for integration #bug !high @item:ANS-1792773060904443

## Verification

Run the affected complete test files after their regression tests. Run role Molecule if the role provides a scenario. Run the complete local `make check`, independent security review and exact-head protected hosted checks. Retain each failed attempt as failed evidence. Close tasks only after the required checks pass.
