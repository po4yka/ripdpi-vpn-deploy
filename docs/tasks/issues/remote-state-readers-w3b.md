---
id: TFR-1795357890236562
title: Read OpenTofu state through the encrypted backend in every script
kind: feature
status: review
area: terraform
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: [TFR-1795328481774241]
spec_mode: required
openspec_change: tfr-1795357890236562-remote-state-readers-w3b
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

Every script that reads OpenTofu state gets it through an in-memory `state pull` from the encrypted backend, and the label-gated disposable CI deploy works again without a bucket identity.

## Acceptance criteria

- No script reads `terraform.tfstate`, `terraform.tfstate.d/<ENV>/terraform.tfstate` or an operator-supplied state path; `--state`, `STAGING_CLEANUP_STATE` and `provider_state_path` are gone.
- A missing workspace, backend, credential or decryption failure refuses; only an existing empty workspace reads as no state.
- Digest bindings use the pulled bytes and the manifest provider and environment.
- The disposable CI deploy initializes with a per-run encrypted local backend; its recovery bundle carries the state and passphrase.
- The affected unit tests and `make check` pass.
