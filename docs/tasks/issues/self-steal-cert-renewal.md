---
id: SCR-1793858662430806
title: Renew the REALITY self-steal certificate off-node on a schedule
kind: feature
status: backlog
area: scripts
priority: medium
risk: standard
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1793858662430806-self-steal-cert-renewal
created: 2026-11-05
updated: 2026-11-05
related_tasks: []
---

## Goal

The P0 self-steal certificate is reissued off-node before it expires, into a new SOPS document ready for a reviewed deploy, without DNS credentials on the node.

## Acceptance criteria

- No CA contact while more than 30 days remain; no repeated issuance while a renewed document exists.
- A due pair is written only into a new encrypted document; the source is unchanged and no issued key stays on disk.
- A wrong name, key, lifetime, lego version, or a hostname shared with nginx-XHTTP is refused.
- The optional daily operator job is installed only with both documents named.
