---
id: VPD-1787496384518490
title: Make vpnd the single authority for the decrypted secrets path and redaction
kind: bug
status: doing
area: vpnd
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: vpd-1787496384518490-vpnd-secrets-path-authority
created: 2026-08-23
updated: 2026-08-24
related_tasks: []
---

## Goal

One resolved decrypted-secrets path everywhere: make receives it explicitly, doctor redacts it on every export surface, hardening failures abort, and permission gates read what they stat. Removes the macOS-without-XDG_RUNTIME_DIR breakage and revives a silently dead security control.

## Audit evidence

| Finding | Evidence |
|---|---|
| Path divergence vs make decrypt | vpnd/src/config.rs:57-64 vs Makefile:17 and scripts/decrypt-secrets.sh:16 |
| Doctor redaction matches only legacy /tmp shape | vpnd/src/commands/doctor.rs:172; tests lock it in via tests/proptest_redact.rs:38 and tests/doctor_bundle.rs:14-24 |
| --ai prompt skips redaction entirely | doctor.rs:45,55 vs bundle path redaction at doctor.rs:125,131 |
| secure_secrets_file swallows chmod errors | config.rs:87-93 (`let _ = set_permissions`); call sites share.rs:61, preflight.rs:25, reconverge.rs:63 |
| Check-then-read permission gate | secrets.rs:82-101; same pattern share.rs:164-168 |

## Acceptance criteria

- With XDG_RUNTIME_DIR unset, `vpnd share <client>` decrypts once and succeeds; second run does not re-decrypt.
- reconverge passes a VPN_SECRETS_FILE that exists and equals vpnd's resolved path.
- Bundle AND AI-prompt outputs mask lines containing the resolved secrets path (tests cover non-/tmp shapes).
- Injected chmod failure aborts share/preflight/reconverge nonzero.
- Gate rejects symlink-swapped or bad-mode files when opened through the held handle.
