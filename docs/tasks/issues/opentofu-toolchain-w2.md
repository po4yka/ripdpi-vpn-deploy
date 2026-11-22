---
id: TFR-1795328347526492
title: Migrate the Terraform toolchain to OpenTofu
kind: feature
status: doing
area: terraform
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: []
spec_mode: required
openspec_change: tfr-1795328347526492-opentofu-toolchain-w2
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

Every root, script, Make target, CI job and vpnd command uses one exact OpenTofu pin instead of Terraform, so W3 can encrypt state on the client.

## Acceptance criteria

- `mise.toml`, workflows and `required_version` name one exact OpenTofu release; no `terraform` binary call remains.
- Lock files are regenerated from the OpenTofu registry for CI and operator platforms.
- `make check -j 4` and the vpnd checks pass.
- Authorized: each production root plans with no changes against its current local state.
