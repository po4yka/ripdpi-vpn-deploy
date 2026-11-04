---
id: SEC-1793770690402026
title: Add daily dependency and image security checks with notifications
kind: feature
status: review
area: security
priority: high
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: daily-security-checks
created: 2026-11-04
updated: 2026-11-04
related_tasks: []
status_detail: Implementation and scoped checks complete; full macOS parity has baseline failures. Full Linux or hosted CI and real notification delivery remain unverified.
---

## Goal

Detect new advisories in unchanged dependencies and pinned images each day,
notify the owner through GitHub, and extend the explicit host audit with
private systemd isolation diagnostics.

## Acceptance criteria

- Daily and manual scans cover Python, npm (including development dependencies),
  Go and the complete existing image inventory, with no weakened image gate.
- New or changed findings and failed/incomplete scans create or update an
  owner-assigned issue; unchanged results are quiet and only complete clean
  recovery closes the issue.
- The explicit audit records analyzer return code, stdout and errors at 0640;
  failures are non-blocking and check mode creates no collection evidence.
- Behavior regressions, workflow checks, the local gate and independent review
  are recorded. Fixtures are not described as hosted delivery or live proof.
- Cloudflare, SSH, fleet access, publishing and deployment remain outside scope.
