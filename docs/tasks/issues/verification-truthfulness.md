---
id: TST-1787497001212692
title: Make verification reflect deployed state
kind: bug
status: blocked
area: testing
priority: high
risk: standard
owner: Ansible implementation
parent: null
blocked_by: []
spec_mode: required
openspec_change: tst-1787497001212692-verification-truthfulness
created: 2026-08-23
updated: 2026-08-27
related_tasks: []
status_detail: Runtime implementation is committed separately on codex/complete-high-review at 374b5f7 and is not included in this main integration. Accessible nodes and the required live/staging acceptance are missing; all three matching inventory server peers are offline. OPS additionally requires live-inventory dry-run BEFORE MERGE.
---

## Goal

Verification tooling asserts the state deploy actually produced for every supported host class: subscription-only gating for verify/smoke transport assertions, revision comparison in source-drift, parameterized and fallback-inclusive listener checks, idempotence phases in full-stack scenarios, an amneziawg scenario that executes real role tasks, TESTING.md rows matching observed sequences, and a single-SSH-listener assertion. See openspec/changes/tst-1787497001212692-verification-truthfulness/.

## Acceptance criteria

- All ten execution steps in the linked change are checked with recorded evidence.
- Full-stack idempotence phases pass (second converge changed=0); verify/smoke complete on subscription-only profiles.
- docs/TESTING.md row-by-row audit matches molecule.yml sequences.

## High-priority implementation ownership

- The Ansible subagent owns verify/smoke/source-drift behavior, Molecule sequences, focused tests, and affected snapshots; shared TESTING.md is reserved for the primary agent.
- The primary agent serializes task/OpenSpec records, generated board, Makefile, shared CI/toolchain files, documentation inventory, staging, commits, and remote delivery. Agents do not commit or mutate credentials/infrastructure.
- Worktree: `codex/complete-high-review`. All writers preserve unrelated changes and coordinate shared-file edits.
