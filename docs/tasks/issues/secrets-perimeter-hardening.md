---
id: SEC-1787496747898735
title: Close secrets-handling and perimeter hardening gaps
kind: bug
status: blocked
area: security
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787496747898735-secrets-perimeter-hardening
created: 2026-08-23
updated: 2026-08-27
related_tasks: [ANS-1787463116251274]
status_detail: Review fixes committed; required systemd/Molecule runtime and fleet dry-run/live checks remain unverified.
---

## Goal

Shipped security behavior matches the repo's written conventions: the dns-morph signing-key render is log-suppressed, both root scheduled units carry the systemd sandbox floor, perimeter ICMP follows the shaping floor, scheduled work is timer-only, the WARP repository key pin is mandatory, browser-facing vhosts share one header baseline, and rate limiting has exactly one documented enforcement layer. See openspec/changes/sec-1787496747898735-secrets-perimeter-hardening/.

## Acceptance criteria

- All eight execution steps in the linked change are checked with recorded evidence.
- security-verify gains passing assertions for ICMP shaping; no secret material appears in verbose deploy output.
- `make ci-fast` and `make validate` green on the final SHA.

## Review ownership

- The Ansible reviewer owns affected Ansible roles/playbooks, their Molecule scenarios, focused Python tests, and corresponding golden snapshots.
- The primary agent serializes Makefile, task/OpenSpec records, generated board, evidence updates, staging, commits, and remote delivery. Reviewers do not commit or change production settings.
