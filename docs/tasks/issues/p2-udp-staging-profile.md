---
id: ANS-1795351855549662
title: Add a disposable staging profile for the p2-udp transports
kind: feature
status: review
area: ansible
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795351855549662-p2-udp-staging-profile
created: 2026-11-22
updated: 2026-11-22
related_tasks: [ANS-1795259263103243]
---

## Goal

A disposable staging node dry-runs the `vpn-p2-udp` transport set through the canonical deployment controller with staging secrets only, so `ANS-1795259263103243` can record its p2-udp dry-run. The new cohort `vpn-p2-udp-staging` equals `vpn-p2-udp` with monitoring, watchdog and backup off and uses the generated staging origin.

## Acceptance criteria

- `ansible/group_vars/vpn-p2-udp-staging.yml` equals the `vpn-p2-udp` map except the three roles, and a test pins that.
- The profile is a family profile and `scripts/check-deploy-profile.py` passes.
- Its listener manifest equals the `vpn-p2-udp` manifest.
- Its origin renders to the origin that `scripts/ci-bootstrap-secrets.sh` writes.
- `docs/reference/deploy-profiles.md` names the profile and its dry-run inputs.
