---
id: SEC-1791735853691219
title: Repair project audit security and lifecycle defects
kind: bug
status: review
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: project-audit-repairs
created: 2026-10-11
updated: 2026-10-11
related_tasks: []
status_detail: CI root causes and scanner findings repaired with local regressions; hosted confirmation pending on the updated PR head.
---

## Goal

Repair the sixteen audit cases with exact identity, resource scope and complete publication, then prepare one reviewed PR.

## Acceptance criteria

- Every REQ-AUDIT requirement has a behavioral regression and an in-scope implementation.
- Focused tests, reviewed snapshots, make check and independent review have recorded outcomes.
- The PR contains only owned repair changes; exact-source CI is recorded separately.
- No live deployment or credential operation is part of source acceptance.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.
