---
id: MON-1794126016474351
title: Make Telegram alert messages readable and actionable
kind: feature
status: doing
area: monitoring
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: mon-1794126016474351-telegram-alert-messages
created: 2026-11-08
updated: 2026-11-08
related_tasks: []
---

## Goal

Telegram alert messages show what failed, where, since when and what to check first.

## Acceptance criteria

- Primary alerts are valid Telegram HTML with readable times and a link to the exact runbook section.
- Every alert rule has an action and an anchored runbook section.
- A Kuma HTML template and monitor descriptions are documented.
- Local checks pass. Deployment and real Telegram delivery need separate authorization.
