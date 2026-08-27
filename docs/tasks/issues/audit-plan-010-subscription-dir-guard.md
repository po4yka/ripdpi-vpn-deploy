---
id: SEC-1787495859810397
title: Validate SUBSCRIPTION_DIR before remote sudo commands
kind: bug
status: done
area: security
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-27
spec_reason: regression-tested-single-module
related_tasks: []
status_detail: Implementation and targeted regressions passed; exact-source hosted CI and final closure remain pending.
closed_at: "2026-08-27T14:12:47Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Subscription path rejection tests cover unsafe syntax and traversal before any Terraform or remote command executes. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

Both token/bootstrap issuers validate `SUBSCRIPTION_DIR` against a conservative absolute-path allowlist before any terraform/sops/ssh activity, so metacharacters can never cross into remote root shell commands.

Execution plan: `plans/010-subscription-dir-validation.md`.

## Acceptance criteria

- Malicious-value probes (quote, relative, `..`) exit 2 before any side effect in both scripts.
- A legitimate value passes the guard (later environmental failure acceptable and recorded).
- `bash -n` x2 + `make shellcheck` clean.
