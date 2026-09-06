## Purpose

Schedule every affected CI consumer while preserving fail-closed protected-main admission.

## ADDED Requirements

### Requirement: REQ-CI-SELECT — Complete dependency selection

The planner MUST select transitive consumers of every changed PR path, including
original rename/deletion paths, embedded documentation and shared dependencies.

#### Scenario: Complete PR history

- **WHEN** a PR contains several commits and its base advances independently
- **THEN** selection covers the entire base-to-merge diff and excludes base-only edits.

#### Scenario: Embedded documentation

- **WHEN** Rust-embedded documentation changes
- **THEN** all Rust consumers run together with baseline checks.

### Requirement: REQ-CI-FALLBACK — Conservative execution

The planner MUST select all consumer groups for main pushes, manual runs,
unknown paths, empty diffs and unavailable or invalid Git history. Baseline lint,
security checks, task contracts, validators and all pytest shards MUST always run.

#### Scenario: Uncertain history

- **WHEN** the base cannot be resolved as an ancestor of the tested merge
- **THEN** all checks are selected without guessing a smaller range.

### Requirement: REQ-CI-GATE — Strict admission

The aggregate gate MUST require success from every selected group and permit
only explicitly unselected groups to be skipped. It MUST reject planner failure,
malformed or partial plans/results, cancelled checks and unexpected skips.

#### Scenario: Selected job skipped

- **WHEN** a selected check is skipped or cancelled
- **THEN** the aggregate gate fails and protected main cannot admit the PR.

#### Scenario: Valid selective run

- **WHEN** all selected groups succeed and only unselected groups skip
- **THEN** the aggregate gate succeeds.

### Requirement: REQ-CI-PROTECTION — Verified protection migration

Required contexts MUST become the planner, aggregate gate and unconditional
checks only after a full hosted run succeeds. Strict mode, existing app bindings
and unrelated protection settings MUST remain intact. Delivery MUST include
observed selective CI and full CI on the exact main revision.

#### Scenario: Context migration

- **WHEN** required contexts are migrated
- **THEN** readback matches the canonical context set and preserved settings.

#### Scenario: Rollback

- **WHEN** dependency scheduling is reverted
- **THEN** restore unconditional scheduling and the preceding required context
  set together after a successful full run; never disable admission protection.

#### Scenario: Compatibility boundary

- **WHEN** this CI-only change is delivered
- **THEN** deployed infrastructure, secrets and public CLI contracts are unchanged,
  while consumers of old required-check names must use the new canonical set.
