---
id: SEC-1787843484501357
title: Require UpCloud provider firewall activation
kind: bug
status: doing
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787843484501357-upcloud-firewall-activation
created: 2026-08-27
updated: 2026-08-27
related_tasks: []
---

## Goal

UpCloud servers explicitly activate their configured provider firewall, so the SSH source allowlist and public listener contract are enforced rather than stored as inactive rules.

## Acceptance criteria

- A mock-provider regression fails when firewall activation is omitted and passes with explicit activation.
- DNS reply regressions prove exact resolver/source-port/destination/ephemeral-port scope, placement before both denies, secondary-address isolation, and invalid-input rejection.
- All UpCloud mock-provider tests and relevant formatting and validation gates pass.
- A separately authorized live rollout preserves existing narrow SSH CIDRs and listeners, reports no server replacement, and verifies firewall activation and authenticated connectivity.
- Local tests do not count as live deployment evidence; the task stays open until required evidence is complete.

## Ownership

- The implementation agent owns only the isolated worktree's UpCloud Terraform source, existing native test files, and provider guidance. It does not modify portfolio or OpenSpec state.
- The primary agent owns this task, its linked OpenSpec artifacts, integration and generated board changes. Independent review is read-only. No live Terraform actions or host changes are authorized in this source-fix lane.
