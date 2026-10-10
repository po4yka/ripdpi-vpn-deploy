# EPC-1791618453830051: Deliver isolated reliable and upgradeable four-protocol connectivity

## Objective

Deliver isolated reliable and upgradeable four-protocol connectivity. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- Child OpenSpec changes and their exact owned runtime/schema/client/test scopes
- Existing reviewed remediation change records are read-only inherited evidence
- NEW audit-coverage.md and roadmap.md within this linked change; no separate process task
- Shared schemas, Makefile, CI selectors, snapshots and portfolio metadata have one serialized integration owner
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] EPC-1791618459636532 Deliver baseline destination isolation authoritative device and endpoint contracts with complete positive and security regression coverage #epic !high @item:EPC-1791618453830051
- [ ] EPC-1791618460420156 Deliver complete runtime authority recovery topology supervision and inherited lifecycle regression proof #epic !high @item:EPC-1791618453830051
- [ ] EPC-1791618461249475 Deliver eligible stable runtime and supported optional transport cohorts with real client traffic and rollback #epic !high @item:EPC-1791618453830051
- [ ] EPC-1791618462520842 Complete requirement-scoped exact-source acceptance and retain unresolved external or physical gates without false closure #epic !high @item:EPC-1791618453830051

## Verification

- `./taskctl graph --json`
- `env -u MAKEFILES -u MAKEFLAGS -u GNUMAKEFLAGS -u MFLAGS make task-check`
- `NEW make transport-native-acceptance on isolated Linux after implementation`
- `build-gate -- make check after implementation`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
