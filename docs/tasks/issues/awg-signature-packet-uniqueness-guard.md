---
id: ANS-1795705936932681
title: Refuse AmneziaWG signature packets that repeat across nodes or match a public default
kind: feature
status: backlog
area: ansible
priority: medium
risk: standard
owner: Planner
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795705936932681-awg-signature-packet-uniqueness-guard
created: 2026-11-26
updated: 2026-11-26
related_tasks: []
---

## Goal

Production generates the AmneziaWG signature packets per instance. It refuses a packet that is byte-identical on two nodes or equal to a publicly known upstream default.

## Acceptance criteria

- Instance creation generates each signature packet from a cryptographic random source within the admitted bounds.
- The production guard refuses an instance set in which a static packet part repeats on two instances or hosts.
- The production guard refuses a packet whose digest matches the pinned list of public default digests.
- The repository stores digests of the public defaults, not the packets.
- Staging keeps the measurement exception that the header guard has.
