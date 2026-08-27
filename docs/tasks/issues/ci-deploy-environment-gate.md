---
id: CIC-1787415665884975
title: Gate credentialed CI deploys behind environment approval
kind: bug
status: done
area: ci
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1787415665884975-ci-deploy-environment-gate
created: 2026-08-22
updated: 2026-08-27
related_tasks: []
status_detail: Implementation and local approval-gate checks passed; protected-main PR and exact-SHA hosted CI still pending.
closed_at: "2026-08-27T12:08:49Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Exact implementation 984b452: full make check passed; hosted CI 33069634871 succeeded with all required checks; required-reviewer environment API check passed. No credentialed deployment claimed."
---

## Goal

A `ci-real-deploy` PR label alone must never expose provider credentials and
the CI age key to job execution. Both credentialed deployment workflows
(`real-vps-deploy.yml`, `transport-reachability-matrix.yml`) require an
approved GitHub deployment on a protected environment before any step runs,
and deploy key material reaches the shell only through step-level `env:` —
never through direct `${{ secrets.* }}` expansion inside `run:` blocks.

## Acceptance criteria

- Both credentialed jobs reference the `ci-real-deploy` GitHub Environment;
  the environment exists with a required-reviewer protection rule.
- No `${{ secrets.` interpolation appears inside any `run:` block of either
  workflow; key material is transferred via step-level `env:` and quoted
  shell variables.
- A focused contract test fails when either invariant regresses.
- Fork short-circuit steps remain as defense in depth.
- Operator-visible behavior is documented: every trigger (label, dispatch,
  schedule) waits for reviewer approval on the environment.

## Review ownership

- The primary agent owns credentialed workflow gating, its focused tests, and operator documentation.
- The primary agent serializes Makefile, task/OpenSpec records, generated board, evidence updates, staging, commits, and remote delivery. Reviewers do not commit or change production settings.
