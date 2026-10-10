# SCR-1791618188806822: Detect client payload drift from every consumed private input

## Objective

Detect client payload drift from every consumed private input. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- scripts/client-drift.py
- scripts/issue-sub-token.sh
- scripts/emit-bundle.sh
- scripts/emit-awg.sh
- scripts/emit-singbox.sh
- secrets/schema.json
- tests/unit/test_client_drift.py
- tests/unit/test_client_registry.py
- openspec/specs/clients/config-registry/spec.md
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] SCR-1791618347514825 Implement consumed-input canonical identity and every drift verdict boundary #bug !high @item:SCR-1791618188806822
- [ ] SCR-1791618349798761 Bind issuance and refresh to exact private artifact identity with atomic-failure regressions #bug !high @item:SCR-1791618188806822
- [ ] SCR-1791618352269556 Enforce private authority and diagnostic boundaries and pass complete source gates #bug !high @item:SCR-1791618188806822

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_client_drift.py tests/unit/test_client_registry.py`
- `build-gate -- make check`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
