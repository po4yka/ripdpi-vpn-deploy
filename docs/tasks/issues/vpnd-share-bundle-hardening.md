---
id: VPD-1787497073989478
title: Harden share bundle token handling and file permissions
kind: bug
status: doing
area: vpnd
priority: high
risk: high
owner: vpnd implementation
parent: null
blocked_by: []
spec_mode: required
openspec_change: vpd-1787497073989478-vpnd-share-bundle-hardening
created: 2026-08-23
updated: 2026-08-27
related_tasks: []
---

## Goal

`vpnd share` produces usable bundles only: tokens are non-empty and validated, missing subscription hosts are hard errors, and every bundle byte lands 0600 through crash-safe writes including QR SVGs.

## Audit evidence

| Finding | Evidence |
|---|---|
| Empty token passes validation | share.rs:40-50 (`chars().all()` vacuously true on ""), read_token trim at share.rs:156-173 |
| Host falls back to literal "(unset)" | share.rs:83-87; URLs built at share.rs:92-97 |
| Stale .tmp bricks future runs | write_private create_new(true) without cleanup, share.rs:181-193 |
| QR SVGs world-readable; temp umask window | qr.rs:12 plain fs::write of token-bearing payload; temp created before mode set at share.rs:184-190 vs 0600 files at share.rs:111,126 |

## Acceptance criteria

- Empty/whitespace token via stdin or file exits nonzero naming the source; no bundle written.
- Missing server_name exits nonzero naming the secrets key; no "(unset)" URLs possible.
- Re-run after simulated crash mid-write succeeds; failed write leaves no temp residue.
- All bundle artifacts incl. qr.svg / qr-ripdpi.svg are mode 0600.

## High-priority implementation ownership

- The vpnd subagent owns vpnd source/tests and vpnd documentation for share/probe-matrix hardening and audit coverage.
- The primary agent serializes task/OpenSpec records, generated board, Makefile, shared CI/toolchain files, documentation inventory, staging, commits, and remote delivery. Agents do not commit or mutate credentials/infrastructure.
- Worktree: `codex/complete-high-review`. All writers preserve unrelated changes and coordinate shared-file edits.
