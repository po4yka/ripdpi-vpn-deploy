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
updated: 2026-08-30
related_tasks: []
status_detail: Nine of ten execution steps are complete. Full-stack and published idempotence passed on exact 4580f9927ed808b4f71b8fa5e0e036890f6daaf2 with changed=0; documentation parity and socket-activated single-SSH-listener acceptance passed on exact b9858085df8073f725670e2acfa0f0bb9cda41da. The remaining blocker is an authorized live verify/source-drift cycle against the deployed exact revision.
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

## Bounded smoke implementation ownership — 2026-08-28

- The smoke agent owns `ansible/playbooks/smoke-test.yml`, focused local Ansible smoke regression coverage, and the relevant existing planning/evidence for `TST-1787496118906712` in `codex/high-smoke-cleanup-20260828`. The shared playbook implements cleanup and subscription-only gating together; the two portfolio records retain their separate acceptance boundaries.
- Other playbooks, transport defaults/ports, Make, SSH, backup, production and other worktrees remain outside this slice. Source tests use temporary local executables; no host/provider operation or whole-task close is authorized here. The primary agent retains integration, generated board/counts and live acceptance.

## Verification host-class implementation ownership

- The Ansible subagent owns only subscription-only predicates in verify.yml, corresponding source-task regressions in test_listener_contract.py, and this step's existing planning/evidence on codex/high-verify-hostclass-20260828 from a823ed2. Step TST-1787496118906453 covers the eleven currently unguarded transport tasks, not just the older six-group inventory.
- Other source, SSH/watchdog execution, source drift, Molecule, toggle defaults, generated counts/board and Git delivery remain with the primary agent. No host operation or portfolio close is part of this slice.

## Published scenario prerequisites ownership — 2026-08-29

- The scenario subagent owns only `ansible/molecule/full-stack-published/molecule.yml`, its input/dependency regressions in `tests/unit/test_molecule_dependencies.py`, and this prerequisite refinement of step `TST-1787496118906321`, in `codex/high-published-prerequisites-20260829` from `fc3acc6`.
- Baseline, SSH, shared full-stack verification, Make, host port mappings, other worktrees and Git delivery remain outside this slice. Fixing scenario inputs does not complete idempotence or the required whole-Molecule/live acceptance; the portfolio remains blocked.

### AWG role scenario slice

- `codex/high-awg-role-molecule-20260828` owns only step `TST-1787496118906595`: the amneziawg default Molecule scenario, adjacent amneziawg unit tests, role rationale, and this step's planning/evidence. Production role tasks, shared CI/Makefile, board/counts, other verification slices, commits and delivery remain with their existing owners.
- Synthetic local Git repositories and no-TUN tools are fixture inputs, never upstream build or real tunnel evidence. The role itself must produce installed artifacts, build receipts, configuration and service state. The parent task remains blocked pending its other acceptance gates.

### Xray idempotence slice

- After the AWG slice, the same worktree owns step `TST-1787496118907291` as a separate change: Xray's default converge/sequence and the adjacent idempotent-converge regression in `tests/unit/test_config_rollback_backup.py`. Production roles, baseline, full-stack scenarios and shared CI remain outside this ownership.
- The repeated converge preserves the role-owned runtime symlinks and reports zero changes. Local filesystem replay and a complete isolated x86_64 QEMU-backed Molecule run now cover this step; external traffic, staging and live-host acceptance remain outside that evidence.
