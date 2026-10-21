---
id: SEC-1792581431602723
title: Close second deployment audit secrets and lifecycle gaps
kind: bug
status: doing
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1792581431602723-close-second-deployment-audit-gaps
created: 2026-10-21
updated: 2026-10-21
related_tasks: []
---

## Goal

Close the four defects that the second pre-deployment audit found at
`03033beb`: plaintext secrets left by an interrupted vpnd pipeline, an in-place
Vultr OS reinstall, verification plays without an environment check, and a
duplicate Hetzner SSH key for a second environment.

## Acceptance criteria

- An interrupt of `vpnd deploy` or `vpnd reconverge` at any step after decrypt
  runs `make clean`, starts no later step and exits with 128 plus the signal.
- A Vultr plan with a changed `os_id` for an existing node refuses.
- `smoke-test.yml`, `verify.yml` and `security-verify.yml` refuse a host whose
  inventory `env` is not `ENV` before any other task.
- A Hetzner environment can reuse an existing project key with the same public
  key; existing state moves without change.
- Each regression fails on its parent commit; focused and complete local checks
  pass and an independent review is recorded.

## Boundaries

No deployment, provider call, credential rotation or change to existing
security gates.
