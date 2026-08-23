---
id: SEC-1787496881680472
title: Establish single-owner sshd configuration layers
kind: bug
status: backlog
area: security
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787496881680472-sshd-config-ownership
created: 2026-08-23
updated: 2026-08-23
related_tasks: []
---

## Goal

Every sshd directive on managed nodes has exactly one owning file, cross-file duplication fails convergence, validation evaluates the effective assembled configuration, and SSH algorithm negotiation is pinned at the managed layer and asserted post-converge — eliminating the silent-shadow trap between the cloud-init and baseline drop-ins. See openspec/changes/sec-1787496881680472-sshd-config-ownership/.

## Acceptance criteria

- All six execution steps in the linked change are checked with recorded evidence.
- Baseline molecule matrix passes on both pinned distros; scratch-node lockout rehearsal succeeds with custom port plus pinned algorithms.
- verify.yml effective-config assertions pass fleet-wide.
