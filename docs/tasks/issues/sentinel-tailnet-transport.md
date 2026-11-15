---
id: SCR-1794726174976734
title: Reach the cloud liveness sentinel over its Tailnet address
kind: feature
status: review
area: scripts
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1794726174976734-sentinel-tailnet-transport
created: 2026-11-15
updated: 2026-11-15
related_tasks: []
status_detail: Production node-b prepare, dry-run and deploy at da6fb86d passed over the Tailnet sentinel route
---

## Goal

A production deploy proves its target through the cloud liveness sentinel over the sentinel's Tailnet address when the operator's public source is not admitted, and the reached sentinel stays bound to its Terraform-state server.

## Acceptance criteria

- The scope check admits a Tailnet sentinel route only when the inventory alias key equals the state public-address key.
- Public routes keep working; other transports are refused.
- A production `node-b` prepare, dry-run and deploy pass with sentinel `node-a` on its Tailnet route.
