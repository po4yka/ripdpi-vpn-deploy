# TST-1791618376497512: Upgrade verified recipient parsers to the current stable client line

## Objective

Upgrade verified recipient parsers to the current stable client line. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- scripts/check-singbox-client-compatibility.py
- tests/unit/test_emit_singbox_roundtrip.py
- tests/unit/test_liveness_profiles.py
- docs/TESTING.md
- tools/tasking or unrelated vpnd migration are OUT OF SCOPE
- .github/workflows/ci.yml
- .github/actions/setup-disposable-ci/action.yml
- scripts/ci-real-deploy.py
- Makefile
- All exact-version expected-value tests discovered from the existing sing-box pin; runtime/source code unrelated to parser consumers is out of scope
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] TST-1791618385464569 Select and verify stable parser artifacts with exact architecture and rollback tests #feature @item:TST-1791618376497512
- [ ] TST-1791618386942234 Migrate full recipient parsing and supported engine routes with real baseline traffic #feature @item:TST-1791618376497512
- [ ] TST-1791618388220484 Publish atomic verified parser adoption and exact source compatibility evidence #feature @item:TST-1791618376497512

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_emit_singbox_roundtrip.py tests/unit/test_liveness_profiles.py`
- `Dependency-provided make transport-native-acceptance on isolated Linux with recorded candidate client identities`
- `build-gate -- make check`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
