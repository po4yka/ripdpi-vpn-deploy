---
id: ANS-1792776076428131
title: Deliver AWG range and signature profiles across server and client
kind: feature
status: doing
area: ansible
priority: high
risk: high
owner: transport-resilience
parent: null
blocked_by: []
spec_mode: required
openspec_change: awg-range-signature-profile
created: 2026-10-23
updated: 2026-10-23
related_tasks: ["po4yka/RIPDPI#TRN-1792776081374051"]
---

## Goal

Deliver header ranges and signature packets from the server authority to the Android AWG engine without loss.

## Acceptance criteria

- One strict profile controls schema, validation, render, export, import, and cohort identity.
- Real upstream peer traffic proves the supported range and signature parameters.
- Malformed or unsupported profiles fail before publication; S3/S4 remain zero.
- Local source gates and exact-head hosted checks pass before merge.
- Physical arm64, constrained path, and fleet rollout remain explicitly unverified until observed; source proof cannot close those observations.

## Ownership

The primary writer owns this repository and the canonical shared contract. The client AWG worker owns the paired Rust and Kotlin consumer in a separate worktree. Other workers own Xray acceptance and certificate verifier builds. Contract mirrors are copied only from the canonical reviewed producer files.
