---
id: TST-1787495860092796
title: Skip age-recovery roundtrip when ssss-combine is absent
kind: bug
status: done
area: testing
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-09-09
spec_reason: test-only
related_tasks: []
closed_at: "2026-09-09T02:31:09Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Local gates: make ci-fast targets green in the worktree (actionlint, zizmor, cloud-init schema, tf-test, tf-policy, yamllint, shellcheck, vpnd-deny, MSRV, 139 golden snapshots, secrets schema, bundle contract, full bats suite, vpnd clippy -D warnings and debug/release tests); make validate green; taskctl validate + make task-check green. Remote CI: exact-main ci.yml run on 2c5544fe20471bc43c649aef2278e3efe34503b6 merged via PR #211 with all pytest groups, codeql and required checks green."
---

## Goal

`tests/bats/age_recovery_roundtrip.bats` skips cleanly with an actionable message when `ssss-combine` is absent (fresh macOS), while CI (which installs ssss) still runs it for real.

Execution plan: `plans/012-age-recovery-ssss-skip.md`.

## Acceptance criteria

- Simulated absence (restricted PATH): all tests skipped, exit 0.
- Tools present: all tests pass.
- `bats tests/bats/` fully green; only the setup() function changed.
