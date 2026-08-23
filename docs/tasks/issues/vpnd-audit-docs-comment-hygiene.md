---
id: DOC-1787497584916859
title: Fix stale doc comments and dead QR helper from audit
kind: bug
status: backlog
area: docs
priority: low
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: docs-only
related_tasks: []
---

## Goal

Doc comments and convention docs match reality: no stale paths, no dead code with misleading comments.

## Audit evidence

| Finding | Evidence |
|---|---|
| secrets.rs doc claims /tmp path shape | secrets.rs:5 "/tmp/vpn-<env>.secrets.yaml" vs actual resolution config.rs:57-64 |
| qr::write_png dead in src with misleading PBM-as-png comment | qr.rs:16-21 comment "renames to .png"; callers only in tests (qr_encode.rs:49-66, share_bundle.rs:116); share.rs:134 comment says SVG-only since 9cc4607 |
| Rust conventions skill claims snapshots live in src/snapshots | .claude/skills/rust-best-practices/SKILL.md vs actual vpnd/tests/snapshots/ |

## Acceptance criteria

- secrets.rs doc names the authoritative resolution (or defers to config.rs).
- write_png either removed with its tests or its comment corrected; no PBM-as-png implication remains.
- Conventions doc points at the real snapshot location.
