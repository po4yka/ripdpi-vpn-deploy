---
id: CIC-1787463116104727
title: Harden CI tooling installs and extend test coverage
kind: chore
status: done
area: ci
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-09-08
spec_reason: tooling-only
related_tasks: []
closed_at: "2026-09-08T08:51:27Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "All five execution steps re-audited against the tree: checksum-verified actionlint/gitleaks installs in .github/workflows/ci.yml, renovate customManagers for xcaddy/caddy, molecule-full-stack as a required gate, serde_yaml_ng 0.10 with no serde_yaml 0.9 left, and the vpnd/promote-spare/listeners.tf coverage; no stubs or placeholders found. remote CI observed green on the pushed final SHA fafb9cf3ff1366f6e657e6ed67e753562fef89ad (PR #86, 57 check runs: 56 success + 1 neutral Trivy config discovery, aggregate 'required checks' success), merged to main as bbb2f4189f4caf28714326b3cfbebe2716fcfdf0."
---

## Goal

Describe the observable outcome.

## Acceptance criteria

Define verifiable completion criteria.
