# SCR-1791617975137354: Make REALITY target validation bounded standards-correct and truthful

## Objective

Make REALITY target validation bounded standards-correct and truthful. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- scripts/validate-reality-target.sh
- scripts/monitor-reality-target.sh
- scripts/reality_target_monitor.py
- scripts/scan-reality-targets.sh
- scripts/CLAUDE.md
- docs/REALITY-TARGET-MONITORING.md
- ansible/roles/reality-self-steal/CLAUDE.md
- tests/unit/test_monitor_reality_target.py
- tests/unit/test_scan_reality_targets.py
- NEW: tests/unit/test_validate_reality_target.py
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] SCR-1791617985610703 Normalize names replace wildcard heuristics and add actual certificate identity regressions #bug @item:SCR-1791617975137354
- [ ] SCR-1791617986915903 Implement bounded stage and aggregate execution with real stalled-process cleanup tests #bug @item:SCR-1791617975137354
- [ ] SCR-1791617987865403 Separate hygiene actual client compatibility and owned public service modes with truthful evidence tests #bug @item:SCR-1791617975137354
- [ ] SCR-1791617989032738 Run target regressions shell and full gates and document promotion authority and remaining vantage gaps #bug @item:SCR-1791617975137354

## Verification

- `mise exec -- python3 -m pytest tests/unit/test_monitor_reality_target.py tests/unit/test_scan_reality_targets.py`
- `make shellcheck`
- `build-gate -- make check`
- `NEW make test-reality-target-validation — Run controlled credential-free real TLS identity client-claim and deadline tests; do not resolve production private targets.`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
