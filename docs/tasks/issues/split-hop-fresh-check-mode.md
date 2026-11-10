---
id: ANS-1794336591509212
title: Let a fresh split-hop node pass the check-mode dry-run
kind: bug
status: doing
area: ansible
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-10
updated: 2026-11-10
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

A fresh split-hop node passes its first check-mode dry-run. Observed on staging Node B: `Enable split-hop egress boot policy loader` failed with "Could not find the requested service split-hop-egress-policy.service", because check mode only planned the unit and the `wireguard-tools` package that ships `wg-quick@`. Node A's `Enable split-hop ingress` task and its restart handler had the same gap.

## Acceptance criteria

- In check mode, both roles skip enabling or restarting a unit whose package or unit file the run only plans; ordinary runs and check mode on a configured host still enable the units.
- A regression test evaluates the real task conditions and fails without the fix.
- Both roles pass Molecule.
