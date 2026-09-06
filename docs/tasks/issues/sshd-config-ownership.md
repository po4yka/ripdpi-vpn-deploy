---
id: SEC-1787496881680472
title: Establish single-owner sshd configuration layers
kind: bug
status: dropped
area: security
priority: high
risk: high
owner: Ansible implementation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787496881680472-sshd-config-ownership
created: 2026-08-23
updated: 2026-09-06
related_tasks: []
status_detail: "Five of six source steps are implemented in the combined protected source delivery: single-owner bootstrap and managed layers, duplicate-owner refusal, assembled effective validation, and exact algorithm pins. The remaining blocker is the required scratch-node custom-port and pinned-algorithm lockout rehearsal followed by fleet verification."
closed_at: "2026-09-06T17:42:11Z"
closed_reason: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed.
evidence_summary: Owner-authorized cancellation only. Existing implementation is retained; no staging, live, client, provider or operational acceptance success is claimed. Prior evidence remains in Git history.
---

## Goal

Every sshd directive on managed nodes has exactly one owning file, cross-file duplication fails convergence, validation evaluates the effective assembled configuration, and SSH algorithm negotiation is pinned at the managed layer and asserted post-converge — eliminating the silent-shadow trap between the cloud-init and baseline drop-ins. See openspec/changes/sec-1787496881680472-sshd-config-ownership/.

## Acceptance criteria

- All six execution steps in the linked change are checked with recorded evidence.
- Baseline molecule matrix passes on both pinned distros; scratch-node lockout rehearsal succeeds with custom port plus pinned algorithms.
- verify.yml effective-config assertions pass fleet-wide.

## High-priority implementation ownership

- The Ansible subagent owns sshd cloud-init/baseline layers, verification playbooks, their focused tests, and affected role snapshots.
- The primary agent serializes task/OpenSpec records, generated board, Makefile, shared CI/toolchain files, documentation inventory, staging, commits, and remote delivery. Agents do not commit or mutate credentials/infrastructure.
- Worktree: `codex/complete-high-review`. All writers preserve unrelated changes and coordinate shared-file edits.
