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
status_detail: Implementation remains on codex/complete-high-review at 37f3a6a50b21e294e5da6048a491d91568cd4627, not main. Recovery restored direct SSH. Read-only P0/P2 manifests still identify an older source revision; exact-source deployment and authorized live verification remain open. Watchdog verification was not invoked because it can restart services.
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

## Listener verification implementation ownership

- The listener subagent owns only `verify.yml` configured Hysteria and Xray/nginx fallback assertions, their local Ansible regressions in `tests/unit/test_listener_contract.py`, and step `TST-1787496118906882` evidence in `codex/high-verify-listeners-20260828` from `7da8b74`.
- SSH, watchdog, liveness, backup, source drift, toggle defaults, Molecule, Makefile, and client contracts are outside this slice. The primary agent serializes TESTING.md, board, full gates, and Git delivery; the portfolio remains blocked on the other steps and required live evidence.

## Full source identity implementation ownership

- The primary agent owns the source-revision equality assertion in `source-drift.yml` and actual-playbook regressions in `test_live_source_revision_contract.py`, in `codex/high-deploy-safety-20260828`. This does not include controller dispatch, live manifest migration, SSH, or watchdog execution. Other worktrees and their test hunks are preserved during integration.
