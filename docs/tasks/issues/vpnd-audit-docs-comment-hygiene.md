---
id: DOC-1787497584916859
title: Fix stale doc comments and dead QR helper from audit
kind: bug
status: done
area: docs
priority: low
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-09-09
spec_reason: docs-only
related_tasks: []
closed_at: "2026-09-09T02:31:09Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Local gates: make ci-fast targets green in the worktree (actionlint, zizmor, cloud-init schema, tf-test, tf-policy, yamllint, shellcheck, vpnd-deny, MSRV, 139 golden snapshots, secrets schema, bundle contract, full bats suite, vpnd clippy -D warnings and debug/release tests); make validate green; taskctl validate + make task-check green. Remote CI: exact-main ci.yml run on 2c5544fe20471bc43c649aef2278e3efe34503b6 merged via PR #211 with all pytest groups, codeql and required checks green."
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
