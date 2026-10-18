---
id: OPS-1792263187492070
title: Restore deployment and VPN rollback reliability
kind: bug
status: done
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: deployment-vpn-reliability
created: 2026-10-17
updated: 2026-10-18
related_tasks: []
status_detail: "All six repairs and regression coverage merged in PR #323 after all 92 CI jobs and nine required contexts passed. Exact protected-main verification is running before closure."
closed_at: "2026-10-18T05:16:11Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "All six repairs merged in PR #323 as 632b42f599c5c6c58c92b44f62b5b95d120b3bc7. Exact protected-main CI 39089475940 passed all 92 jobs, 7902 tests and 45 subtests, 38 Molecule jobs, full integration and 56 separate native cases with cleanup. Both image scans passed with zero findings; no new CodeQL alerts. PR #326 committed the accepted review snapshot in main. Canonical OpenSpec archive passed. No live rollout."
---

## Goal

Repair all six audited deployment and VPN recovery defects with regression coverage; merge the verified source fix without a live rollout.

## Acceptance criteria

- Dependent phases remain serial and dry-run intent is honored.
- State backups select the exact environment.
- Firewall and complete AWG runtime recover coherently after rejection.
- CI descendants cannot survive command cleanup.
- Focused regressions, applicable repository gates, review and exact-source CI pass before merge.
