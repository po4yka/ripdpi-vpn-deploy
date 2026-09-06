---
id: ANS-1787495907091073
title: Fix production-breaking transport convergence defects
kind: bug
status: blocked
area: ansible
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1787495907091073-transport-convergence-critical-fixes
created: 2026-08-23
updated: 2026-08-27
related_tasks: []
status_detail: Source and hosted role checks are complete. A bounded 2026-09-06 passive recheck returned unknown/command-failed for all three inventory aliases; the only online Tailnet peer is not an inventory endpoint, and the strict SSH-context mapping is unavailable. Required fleet dry-run and live convergence remain open.
---

## Goal

Ten production-breaking defects found by the 2026-08-23 cloud-init → Ansible audit are fixed: wg-quick-parseable split-hop hooks, conjunctive WARP health gate, readable shared TLS for hysteria-realm, self-preserving subscription mirror pulls, restart-safe amneziawg lifecycle, check-mode-safe firewall probes, case-insensitive revocation matching, quoted Hysteria YAML scalars, resolvable awg-quick unit dependencies, and bounded honeypot connection hold time. See openspec/changes/ans-1787495907091073-transport-convergence-critical-fixes/.

## Acceptance criteria

- All ten execution steps in the linked change are checked with recorded evidence.
- Per-role molecule scenarios pass before and after each fix; no rendered listener contract changes.
- `make ci-fast` and `make validate` green on the final SHA.

## Review ownership

- The Ansible reviewer owns affected Ansible roles/playbooks, their Molecule scenarios, focused Python tests, and corresponding golden snapshots.
- The primary agent serializes Makefile, task/OpenSpec records, generated board, evidence updates, staging, commits, and remote delivery. Reviewers do not commit or change production settings.
