# SEC-1786336086885514: Resolve all open CodeQL code scanning alerts

## Objective

Fix CodeQL alerts 320 through 327 in source while preserving the local Xray
metrics reader path, fail-closed liveness behavior, and taskctl lifecycle.

## Ownership

Owned paths are the eight alerted Python files, focused tests under
`tests/unit/` and `scripts/tests/`, the monitoring role's tasks/defaults and
Molecule scenario, this OpenSpec change, and its portfolio issue. Shared task
and monitoring files have one writer in the dedicated
`codex/fix-current-code-scanning` worktree.

## Execution

- [x] ANS-1786336382853856 Restrict Xray metric files to 0640, grant node_exporter shared-group access with restart-on-change, and prove fresh and existing-file convergence in unit and Molecule checks #bug !high @item:SEC-1786336086885514
- [x] SCR-1786336382872322 Make exporter fallback-write failure redacted and observable, document bounded socket retry intent, remove unused script imports, and pass focused monitoring and liveness tests #bug !high @item:SEC-1786336086885514 @blocked_by:ANS-1786336382853856
- [x] SEC-1786336382890713 Remove taskctl's overwritten execution assignment and redundant imports, normalize unittest imports, and pass task lifecycle and Vultr preflight regressions #bug !high @item:SEC-1786336086885514 @blocked_by:SCR-1786336382872322
- [x] TST-1786336382909520 Run task-contract validation, the full fast CI gate, monitoring Molecule, make validate, and record every exact local outcome without weakening or skipping a gate #bug !high @item:SEC-1786336086885514 @blocked_by:SEC-1786336382890713
- [ ] CIC-1786336382929709 Obtain hosted codeql python success on the exact implementation SHA and verify alerts 320 through 327 are closed with no replacement alert or dismissal #bug !high @item:SEC-1786336086885514 @blocked_by:TST-1786336382909520

## Verification

Named gates: focused pytest suites for the five affected behaviors,
`make molecule-test ROLE=monitoring`, `make task-check`, `make ci-fast`,
`make validate`, and hosted `codeql (python)` on the exact implementation SHA.
Dry-run, staging, live, client, and artifact evidence are not applicable because
the change does not authorize deployment or publish an artifact.
