---
id: TST-1786299293097217
title: Complete recurring AmneziaWG live acceptance
kind: feature
status: backlog
area: testing
priority: high
risk: high
owner: AWG live acceptance
parent: null
blocked_by: []
spec_mode: required
openspec_change: tst-1786299293097217-complete-recurring-amneziawg-live-acceptance
created: 2026-08-09
updated: 2026-08-09
related_tasks:
  - po4yka/RIPDPI#TRN-1786264762917677
---

## Goal

Close the current-revision AmneziaWG acceptance gap with repeatable, redacted
evidence from a real client and disposable VPS. The lane must distinguish
product failure from unavailable infrastructure and prove recovery behavior,
not merely process or listener health.

## Ownership

- Primary surfaces: the existing real-VPS AWG executor, sentinel integration,
  evidence schema, focused tests, and safe operator documentation.
- Cross-repository coordination: the RIPDPI interoperability task remains the
  client-side authority; this task owns deploy-side execution and evidence.
- Serialized lanes: shared liveness evidence, secrets schema, and recurring
  runner configuration have one writer at a time.

## Acceptance criteria

- A real current-revision client completes authenticated bidirectional TCP and
  UDP traffic through a disposable server.
- The same run proves restart, configuration reload, reconnect/recovery, stale
  key rejection, and deterministic teardown.
- Missing provider inputs, credentials, or runner capacity produce explicit
  blocked evidence and can never green-skip.
- Evidence is freshness-bound, redacted, bound to exact client/deploy commits,
  and accepted by both repositories' contract tests.
- The recurring schedule is observed at least once after the initial manual
  acceptance without exposing endpoints, keys, packet contents, or inventory.

## Verification

- `make task-check`
- Focused AWG provisioning, sentinel, evidence-schema, and source-pin tests
- One isolated real-VPS run plus one observed recurring run
