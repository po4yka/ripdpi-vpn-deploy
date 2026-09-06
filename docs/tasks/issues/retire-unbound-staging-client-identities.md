---
id: SEC-1788639574108602
title: Retire unbound staging client identities after verified cleanup
kind: feature
status: done
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1788639574108602-retire-unbound-staging-client-identities
created: 2026-09-06
updated: 2026-09-06
related_tasks: []
status_detail: Protected main ea94beef contains the source-only retirement controller; 196 focused tests, full local make check and exact-main CI 34024059323 passed. No real secret or provider mutation is in scope.
closed_at: "2026-09-06T10:20:44Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main ea94beef; 196 focused tests, full local make check and exact-main CI 34024059323 passed; source-only OpenSpec archived.
---

## Goal

Provide a supported operator path that revokes an issued staging-only client
after the exact staging resources are already absent, even when disposable
executor binding and promotion artifacts were never created.

## Acceptance criteria

- The operator command authenticates the original staging intent, cleanup
  manifest and provider-absence/state-zero evidence before any encrypted edit.
- Only one exact issued client spanning every required secrets collection and
  all of its Xray cohort references are removed; partial, duplicate, unknown,
  foreign, promoted or still-bound identities are refused without mutation.
- Encrypted mutation is serialized, compare-bound to the original ciphertext,
  atomic and recoverable through a private durable receipt without exposing
  plaintext or secret values. It shares the canonical project lock with
  onboarding, subscription issuance and normal de-onboarding.
- Tests cover successful and idempotent retirement, concurrent/CAS and crash
  recovery, unsafe paths, malformed inputs and mismatched absence evidence.
- The Make entrypoint rejects non-literal inputs and command-line credentials
  before executing the controller.
