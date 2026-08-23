---
id: SEC-1787495848492126
title: Lock down and gitignore credential-bearing QR artifacts
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

Credential-bearing QR artifacts (`*.qr.png` with bearer URLs / client keys) are written owner-only (0600) by all three issuer scripts and are gitignored, closing the world-readable-perms and accidental-commit gaps that gitleaks cannot catch.

Execution plan: `plans/004-qr-artifact-hygiene.md`.

## Acceptance criteria

- `umask 077` set once near the top of `emit-qr.sh`, `issue-sub-token.sh`, `issue-bootstrap.sh`; every file-writing `qrencode` call followed by `chmod 0600`.
- `*.qr.png` added to `.gitignore` with a passing contract test.
- `bash -n` clean on all three scripts; `make shellcheck` exit 0.

