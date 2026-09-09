# Plan 014: Build the taskctl negative-path test harness

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 15267007..HEAD -- scripts/tasks/taskctl.py scripts/tests/test_taskctl.py`
> Re-read the cited regions if they changed since `15267007`.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MEDIUM
- **Depends on**: none (absorbs plan 005's inline probes; folds TASKING-07)
- **Category**: tooling / assurance
- **Planned at**: commit `15267007`, 2026-09-09

## Why this matters

Negative-path coverage for `scripts/tasks/taskctl.py` grew inline: plan 005
slug probes, pre-policy terminal-transition tests, policy-downgrade tests, and
stale-lane tests (CIC-1788896215087324, CIC-1788902865968549). Each bug fix
added one ad-hoc case in its own style. A declared harness turns failure-mode
testing into a matrix, so the next lifecycle change cannot silently remove a
guard. It also resolves TASKING-07 from the 2026-08-23 audit
(OPS-1787495860232652): receipts prove internal consistency, not provenance —
the boundary gets documented, and any future enforcement extension lands on
this harness.

## Current state

- `scripts/tests/test_taskctl.py` — 95 test functions, 101 collected items
  with subtests at `15267007`. Negative cases are interleaved with positive
  tests. Temp-task-root fixture patterns already exist in-file.
- `docs/tasks/README.md` does not yet document the provenance trust boundary.
- The validator is stdlib-only and fail-closed on malformed input via `fail()`.

## Implementation

1. Add a parametrized negative-path matrix in `test_taskctl.py`:
   `(command, argv, expected failure class)` rows driven by one fixture that
   builds a minimal valid task root and then applies one corruption at a time.
2. Port plan 005's inline slug probes into the matrix: `../evil`,
   `/tmp/evil-abs`, empty, uppercase, trailing dot.
3. Add malformed-record rows: missing required section, bad enum value,
   orphaned work record, unknown `related_tasks` ID, bad step marker.
4. Add lifecycle rows: terminal transition without committed review under
   policy v1, purge with a dirty tree, `close prepare` without `--evidence`,
   `blocked_by` cycle.
5. Document the provenance boundary in `docs/tasks/README.md`: committed
   history validation proves internal consistency from the validation base;
   it does not prove provenance of records that predate that base — those are
   operator-trusted.

## Verification

- `python3 -m pytest scripts/tests/test_taskctl.py -q` — collected count grows
  by at least the ported cases; all green.
- `make task-check` and `./taskctl validate` — green.
- `docs/tasks/README.md` carries the boundary paragraph.

## STOP conditions

- A harness case contradicts a documented fail-closed behavior → stop; do not
  weaken the validator to make a test pass.
- The matrix outgrows pytest parametrization clarity → split into a helper
  module, but keep one entry point.
