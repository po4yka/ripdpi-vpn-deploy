---
id: SEC-1787495848492126
title: Lock down and gitignore credential-bearing QR artifacts
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
closed_at: "2026-08-27T14:12:46Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Real filesystem regressions cover fresh and existing 0644 QR outputs: atomic replacement publishes 0600 artifacts; default QR and temporary paths are ignored. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

Credential-bearing QR artifacts (`*.qr.png` with bearer URLs / client keys) are written owner-only (0600) by all three issuer scripts and are gitignored, closing the world-readable-perms and accidental-commit gaps that gitleaks cannot catch.

Execution plan: `plans/004-qr-artifact-hygiene.md`.

## Acceptance criteria

- `umask 077` set once near the top of `emit-qr.sh`, `issue-sub-token.sh`, `issue-bootstrap.sh`; every file-writing `qrencode` call followed by `chmod 0600`.
- `*.qr.png` added to `.gitignore` with a passing contract test.
- `bash -n` clean on all three scripts; `make shellcheck` exit 0.
