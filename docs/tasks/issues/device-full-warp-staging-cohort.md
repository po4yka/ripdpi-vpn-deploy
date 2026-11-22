---
id: ANS-1795357817411977
title: Add a device-full staging cohort with WARP outbound for refresh acceptance
kind: feature
status: doing
area: ansible
priority: high
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795357817411977-device-full-warp-staging-cohort
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

A disposable staging node can run the WARP outbound backend, so SEC-1795260492741288 can check the WARP namespace refresh under the bounded generation unit. The controller reads the `vpn` map only from tracked cohorts and no cohort enables WARP today.

## Acceptance criteria

- `vpn-device-full-warp-staging` equals `vpn-device-full-staging` except the WARP toggle and one route; a test pins this.
- The cohort is a guarded family profile and the deploy profile lint passes.
- One disposable node switches to the cohort after first onboarding, connects WARP after a single operator registration, and passes the refresh and reboot check.
