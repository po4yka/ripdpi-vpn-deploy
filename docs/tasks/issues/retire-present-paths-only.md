---
id: ANS-1795702245344721
title: Retire absent owned paths and units without one remote call per path
kind: chore
status: backlog
area: ansible
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-26
updated: 2026-11-26
spec_reason: mechanical-refactor
related_tasks: []
---

## Goal

Disabled roles retire their owned files and units on every converge and every preview. The timed previews in [the preview cost research](../../research/preview-cost-2026-11.md) show that these retirement loops make one remote call for each declared path or unit, although on a node where the role was never installed almost every path is absent. `runtime-release` retirement already removes only present paths. The other retirement loops get the same treatment, so a preview of an unchanged node spends its remote calls on state that exists.

## Acceptance criteria

- The `file` absent loops in the disable or retire paths of subscription-host (`Remove only exact owned runtime files`, `Remove field-report ingest files and aggregate textfile`), geodata, nginx-xhttp (model news, routing lists), public-site and the hysteria traffic exporter remove only the paths that one prior remote query found present, and still remove every present declared path in a deploy.
- `subscription-host : Inspect exact owned units before retirement` queries all its units in one remote call, and `dns-morph-bridge : Inspect shared Unbound service before retiring its bridge fragment` queries the one unit it needs instead of `service_facts`.
- Behaviour is unchanged: the role Molecule scenarios and the retirement tests pass, and a check-mode preview still reports each present path as changed.
- A timed preview of one production node shows the removed remote calls.
