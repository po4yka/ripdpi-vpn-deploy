---
id: SEC-1787496747898735
title: Close secrets-handling and perimeter hardening gaps
kind: bug
status: backlog
area: security
priority: critical
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787496747898735-secrets-perimeter-hardening
created: 2026-08-23
updated: 2026-08-23
related_tasks: ["ANS-1787463116251274"]
---

## Goal

Shipped security behavior matches the repo's written conventions: the dns-morph signing-key render is log-suppressed, both root scheduled units carry the systemd sandbox floor, perimeter ICMP follows the shaping floor, scheduled work is timer-only, the WARP repository key pin is mandatory, browser-facing vhosts share one header baseline, and rate limiting has exactly one documented enforcement layer. See openspec/changes/sec-1787496747898735-secrets-perimeter-hardening/.

## Acceptance criteria

- All eight execution steps in the linked change are checked with recorded evidence.
- security-verify gains passing assertions for ICMP shaping; no secret material appears in verbose deploy output.
- `make ci-fast` and `make validate` green on the final SHA.
