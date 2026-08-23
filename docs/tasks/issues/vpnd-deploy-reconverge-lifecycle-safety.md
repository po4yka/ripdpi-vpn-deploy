---
id: VPD-1787497317352770
title: Guarantee secrets cleanup and scoped targeting on deploy paths
kind: bug
status: backlog
area: vpnd
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: vpd-1787497317352770-vpnd-deploy-reconverge-lifecycle-safety
created: 2026-08-23
updated: 2026-08-23
related_tasks: []
---

## Goal

Deploy paths never leave plaintext secrets behind, production applies stay scoped to exact targets, documented host resolution actually happens, and summaries stop printing secret-file locations.

## Audit evidence

| Finding | Evidence |
|---|---|
| Failed step skips final clean; plaintext persists | steps end with make::target(ctx,"clean") at deploy.rs:38; `?` loop at deploy.rs:69-71; same shape reconverge.rs:62-87 |
| Registry ipv4 flows verbatim into ansible --limit | reconverge.rs:33-37,66-85; host add accepts arbitrary strings host.rs:21-31 |
| doctor/probe --host never resolved against registry | help claims registry alias cli.rs:137-139,152-155; args.host only interpolated into prompt text doctor.rs:45,84; raw alias passed as HOST probe.rs:17-22 |
| Deploy summary prints sops/secrets file paths | deploy.rs:52-53; contradicts vpnd/CLAUDE.md "Never log it" |

## Acceptance criteria

- Failure-injection test proves cleanup runs after a failed middle step and the original error is preserved.
- Pattern-valued ipv4 (`all`, `prod:*`, malformed octets) aborts reconverge naming the record.
- doctor/probe fail fast on unknown aliases or env/provider mismatch.
- Plan summary snapshot shows placeholders where secret paths used to appear.
