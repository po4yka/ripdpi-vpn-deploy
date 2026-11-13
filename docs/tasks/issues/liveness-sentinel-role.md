---
id: ANS-1794584539221043
title: Prepare a cloud liveness sentinel through an Ansible role
kind: feature
status: review
area: ansible
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1794584539221043-liveness-sentinel-role
created: 2026-11-13
updated: 2026-11-13
related_tasks: []
---

## Goal

A permanent cloud node can be prepared as a protocol-liveness sentinel through an Ansible role that installs the pinned engines and AWG toolchain into role-owned paths and publishes the installed `expected_runtime` pins; the long-lived split-hop Node B enables it.

## Acceptance criteria

- Engines install only after digest and version verification into `/opt/ripdpi-liveness-sentinel/bin`; no path owned by another role is written.
- One pin file feeds the role and the disposable executor flow.
- The native probe finds the role prefix.
- The live Node B differs from the staging Node B by exactly the toggle and its allowlist entry.
