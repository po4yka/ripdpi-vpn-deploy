---
id: OPS-1787496414433523
title: "Harden deploy-path integrity: guards, rollback, rotation"
kind: bug
status: blocked
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1787496414433523-deploy-path-integrity
created: 2026-08-23
updated: 2026-08-27
related_tasks: []
status_detail: "Implementation committed; mandatory live-inventory dry-run BEFORE MERGE and deploy/rotation/rollback rehearsal unavailable: all three matching server peers are offline. This change is not eligible for main integration."
---

## Goal

The operator deploy path enforces its own guarantees on every invocation shape: guards run under any tag scope, deploys wait for bootstrap completion, renderer inputs fail closed at plan time, rotation keeps the rollback restore point current, rollback validates before repointing runtime, failed probes reclaim resources, and maintenance gates depend only on repo-managed facts and locale-independent output. See openspec/changes/ops-1787496414433523-deploy-path-integrity/.

## Acceptance criteria

- All fourteen execution steps in the linked change are checked with recorded evidence.
- Named pytest cases cover tagged guards, renderer rejections, rollback ordering, rotation .prev creation, and toggle-default parity.
- A full deploy-path cycle (wait gate, rotation, rollback rehearsal) completes on live inventory; `make ci-fast`/`make validate` green.

## High-priority implementation ownership

- The primary agent owns site/rotation/rollback/maintenance playbooks, bootstrap and inventory scripts, Makefile, provider variable validation, and shared group defaults.
- The Ansible subagent owns smoke-test cleanup and toggle parity in its verify/smoke playbooks; changes are coordinated with verification-truthfulness.
- Task records, OpenSpec mutations, commits, CI and operator actions remain serialized under the primary agent. Preserve unrelated concurrent changes.
