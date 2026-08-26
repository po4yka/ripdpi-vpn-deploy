---
id: ANS-1787495907091073
title: Fix production-breaking transport convergence defects
kind: bug
status: doing
area: ansible
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1787495907091073-transport-convergence-critical-fixes
created: 2026-08-23
updated: 2026-08-24
related_tasks: []
---

## Goal

Ten production-breaking defects found by the 2026-08-23 cloud-init → Ansible audit are fixed: wg-quick-parseable split-hop hooks, conjunctive WARP health gate, readable shared TLS for hysteria-realm, self-preserving subscription mirror pulls, restart-safe amneziawg lifecycle, check-mode-safe firewall probes, case-insensitive revocation matching, quoted Hysteria YAML scalars, resolvable awg-quick unit dependencies, and bounded honeypot connection hold time. See openspec/changes/ans-1787495907091073-transport-convergence-critical-fixes/.

## Acceptance criteria

- All ten execution steps in the linked change are checked with recorded evidence.
- Per-role molecule scenarios pass before and after each fix; no rendered listener contract changes.
- `make ci-fast` and `make validate` green on the final SHA.
