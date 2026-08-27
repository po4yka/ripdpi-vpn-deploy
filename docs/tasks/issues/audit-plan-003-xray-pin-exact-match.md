---
id: SCR-1787495848362337
title: Match pinned Xray version exactly in probe-matrix-driver
kind: bug
status: done
area: scripts
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-27
spec_reason: regression-tested-single-module
related_tasks: []
status_detail: Implementation and targeted regressions passed; exact-source hosted CI and final closure remain pending.
closed_at: "2026-08-27T14:12:46Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Xray version checks reject prefixes, wrong versions and nonzero version commands; the exact pinned version is accepted. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

`probe-matrix-driver.py` compares the installed Xray version token exactly against the pin, so a stale prefix pin (`v26.3.2` vs installed `v26.3.27`) yields the `version-mismatch` verdict instead of silently passing.

Execution plan: `plans/003-xray-pin-exact-match.md`.

## Acceptance criteria

- No substring containment against the version banner remains in the driver.
- Unit cases cover: exact match passes; prefix pin fails with `version-mismatch`; absent token fails; non-zero returncode fails.
- Full unit suite passes.
