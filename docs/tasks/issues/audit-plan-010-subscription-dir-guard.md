---
id: SEC-1787495859810397
title: Validate SUBSCRIPTION_DIR before remote sudo commands
kind: bug
status: backlog
area: security
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

Both token/bootstrap issuers validate `SUBSCRIPTION_DIR` against a conservative absolute-path allowlist before any terraform/sops/ssh activity, so metacharacters can never cross into remote root shell commands.

Execution plan: `plans/010-subscription-dir-validation.md`.

## Acceptance criteria

- Malicious-value probes (quote, relative, `..`) exit 2 before any side effect in both scripts.
- A legitimate value passes the guard (later environmental failure acceptable and recorded).
- `bash -n` x2 + `make shellcheck` clean.

