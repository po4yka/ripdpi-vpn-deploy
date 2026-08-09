---
id: OPS-1786299564848189
title: Add profile-aware cross-provider warm-spare redundancy
kind: feature
status: backlog
area: operations
priority: high
risk: high
owner: Fleet resilience
parent: null
blocked_by:
  - MON-1786299441667649
spec_mode: required
openspec_change: ops-1786299564848189-profile-aware-cross-provider-warm-spare
created: 2026-08-09
updated: 2026-08-09
related_tasks: []
---

## Goal

Remove the one-provider-per-profile failure mode by adding a provider-independent
warm spare for a critical logical profile and integrating it with the existing
multi-vantage, operator-approved promotion flow.

## Ownership

- Primary surfaces: provider-neutral fleet inventory, Terraform environment
  selection, Ansible profile convergence, liveness binding, rotation state,
  tests, and safe operator documentation.
- Serialized lanes: fleet registry, shared inventory rendering, liveness policy,
  and rotation state have one writer at a time.

## Acceptance criteria

- One critical logical profile has an independently provisioned warm spare on a
  different provider failure domain.
- Active and spare nodes converge from the same reviewed source while retaining
  separate state, credentials, and evidence identities.
- Promotion requires sustained multi-vantage profile failure, a healthy spare,
  exact configuration binding, and explicit operator confirmation.
- Failure, indeterminate evidence, or configuration drift refuses promotion and
  leaves the active path unchanged.
- A staging drill proves promotion, rollback, and cleanup without changing
  production routes automatically.

## Verification

- `make task-check`
- Provider/inventory, convergence, liveness, and rotation tests
- Provider-refreshed dry runs and an isolated staging promotion/rollback drill
