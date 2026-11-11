---
id: SCR-1794387120415327
title: Provision the disposable liveness executor with sentinel runtimes
kind: feature
status: doing
area: scripts
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1794387120415327-disposable-executor-sentinel-runtime
created: 2026-11-11
updated: 2026-11-11
related_tasks: []
---

## Goal

The disposable liveness executor can carry every runtime its four-profile staging sentinel verifies: pinned sing-box and Xray, and the immutable offline-built AWG toolchain. One Make target installs them into the exact live executor and prints the `expected_runtime` for the predeployment liveness configuration. Executor preparation no longer depends on the operator's umask.

## Acceptance criteria

- `make provision-disposable-liveness-runtime` succeeds against a live executor and prints `sing_box`, `xray`, `awg` and `awg_toolchain` observed inside it.
- Engine archives are verified against pinned digests before reaching the executor; the amd64 pins equal the CI pins; AWG sources are the role's commit pins.
- `make prepare-disposable-liveness` succeeds under umask 022.
- Tests cover pins, archive extraction, the vendor archive against the real offline builder, and the umask behaviour.
