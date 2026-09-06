---
id: SEC-1787496747898735
title: Close secrets-handling and perimeter hardening gaps
kind: bug
status: dropped
area: security
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787496747898735-secrets-perimeter-hardening
created: 2026-08-23
updated: 2026-09-06
related_tasks: []
status_detail: Implementation, full local check, and hosted Molecule passed at 984b452; security-verify check-mode and live fleet acceptance blocked by unavailable management access.
closed_at: "2026-09-06T17:42:11Z"
closed_reason: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed.
evidence_summary: Owner-authorized cancellation only. Existing implementation is retained; no staging, live, client, provider or operational acceptance success is claimed. Prior evidence remains in Git history.
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
