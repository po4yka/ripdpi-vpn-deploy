---
id: ANS-1794729221714172
title: Randomise the AmneziaWG wire shape and listen port per instance
kind: bug
status: doing
area: ansible
priority: high
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1794729221714172-awg-per-instance-wire-shape
created: 2026-11-15
updated: 2026-11-15
related_tasks: []
---

## Goal

Every production AmneziaWG instance has generated junk, padding and port values that this repository does not publish, and no header value that is a WireGuard message type. Source: the 2026-11-15 repository audit. `TST-1792263206120096` owns the transport-message padding question and `ANS-1792776076428131` owns header ranges.

## Acceptance criteria

- Instance creation writes generated `jc`, `jmin`, `jmax`, `s1` and `s2` values that satisfy the existing parameter relationships.
- Every secrets document must state the five values; strict validation and transport admission refuse a production instance that has the committed example value set, and a staging document with that set still validates.
- On production the AmneziaWG role refuses any header value from 1 to 4 without a recorded measurement.
- Production validation refuses the WireGuard default port, and the provider legacy listener list opens no AmneziaWG port.
