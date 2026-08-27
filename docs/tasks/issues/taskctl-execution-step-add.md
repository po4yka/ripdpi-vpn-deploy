---
id: CIC-1787849827002217
title: Allocate execution steps through the public taskctl CLI
kind: bug
status: done
area: ci
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-27
updated: 2026-08-27
spec_reason: tooling-only
related_tasks: []
closed_at: "2026-08-27T17:20:25Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Public CLI implemented and independently reviewed; root 86 focused tests plus four subtests, full unit suite 1086 passed with one existing network-scanner skip, strict task contracts and staged gitleaks passed. Actual pinned OpenSpec integration and six-step consumer use passed. Hosted checks remain the protected-branch delivery gate.
---

## Goal

Provide public execution-step allocation for required OpenSpec tasks, unblocking
the SSH access safety implementation tracked by SEC-1787849146785216.

## Acceptance criteria

`taskctl steps <id> add` allocates a unique execution ID through the existing
locked common-directory allocator and writes its owning `@item` backlink.
Only the selected required task may bootstrap an absent `tasks.md`; unrelated
invalid records still fail validation. Existing execution content is preserved.
Regression tests cover allocation, bootstrap, backlinks, and failure boundaries.

## Ownership

The implementation agent owns `scripts/tasks/taskctl.py`, its existing workflow
tests, and concise CLI usage documentation in this isolated worktree. The root
agent owns portfolio records, validation, review, and Git integration. No live
host or provider operations belong to this task.
