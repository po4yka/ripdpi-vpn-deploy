---
id: SEC-1794029167060487
title: Harden server configuration from rollout lessons
kind: bug
status: backlog
area: security
priority: medium
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1794029167060487-server-config-rollout-lessons
created: 2026-11-07
updated: 2026-11-07
related_tasks: []
---

## Goal

Rollouts reproduce from source: the self-steal expiry series follows the installed certificate, observer egress is owned by its firewall renderer, and operator failures name their cause.

## Acceptance criteria

- The agent unit loads the self-steal certificate only when it is installed, and promtool shows the missing-series alert.
- The foundation renders the observer ingress and Telegram egress rules from validated inputs.
- The operator records the failing task name, refuses a busy lock and a missing generated inventory with typed categories.
- `AGENTS.md` matches the restored kit read deny.
