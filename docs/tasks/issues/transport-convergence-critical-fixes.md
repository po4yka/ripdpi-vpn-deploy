---
id: ANS-1787495907091073
title: Fix production-breaking transport convergence defects
kind: bug
status: done
area: ansible
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1787495907091073-transport-convergence-critical-fixes
created: 2026-08-23
updated: 2026-09-06
related_tasks: []
status_detail: All source fixes and protected-main checks are complete. Shared deploy and external protocol acceptance are consolidated in OPS-1787496414433523 and TST-1787850553468536.
closed_at: "2026-09-06T14:01:25Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Transport convergence fixes passed local and protected-main checks; shared deploy and profile acceptance remain in OPS-1787496414433523 and TST-1787850553468536.
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
