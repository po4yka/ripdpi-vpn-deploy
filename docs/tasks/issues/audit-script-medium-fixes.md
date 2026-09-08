---
id: SCR-1787463115839994
title: Fix medium-priority script findings from audit
kind: bug
status: done
area: scripts
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
closed_at: "2026-09-08T08:51:37Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "All four execution steps re-audited against the tree: bash-3.2-safe ${auth[@]+...} at both warm-spare-watcher ntfy call sites, spot-check-secrets exit-2 YAML diagnosis without traceback or content echo plus the CN-parsing guard, and range-vs-range collision detection with allowlist suppression. Review found the CN half of the claimed coverage vacuous (fixture keyed under an uninspected role with unindented block scalars, so the gate exited on invalid YAML before parsing the certificate); fixed in this branch and mutation-verified: removing the CN-presence guard leaves the old test green and turns the corrected test red. remote CI observed green on the pushed final SHA fafb9cf3ff1366f6e657e6ed67e753562fef89ad (PR #86, 57 check runs: 56 success + 1 neutral Trivy config discovery, aggregate 'required checks' success), merged to main as bbb2f4189f4caf28714326b3cfbebe2716fcfdf0."
---

## Goal

Describe the observable outcome.

## Acceptance criteria

Define verifiable completion criteria.
