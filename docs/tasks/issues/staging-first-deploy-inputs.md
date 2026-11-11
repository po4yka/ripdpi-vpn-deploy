---
id: ANS-1794394899306893
title: Let a fresh disposable staging node pass its first deploy inputs
kind: bug
status: doing
area: ansible
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-11
updated: 2026-11-11
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

Observed on staging Node A for `ANS-1794231660855533`: the first `device-full-staging` dry-run refused because `public_site_canonical_url` kept the `all.yml` placeholder while `scripts/ci-bootstrap-secrets.sh` writes `hysteria.masquerade_url` for the node's own XHTTP origin; the CI profile already derives it from `nginx_xhttp.server_name`. The same run then refused on the listener contract because Node A's tfvars listed the split-hop ingress UDP listener before the ingress phase, and an earlier Node B deploy rolled back with `status-rpc-failed` after the operator's public address changed. The guides did not name either step.

## Acceptance criteria

- The three disposable staging cohorts derive `public_site_canonical_url` from `nginx_xhttp.server_name` and the public XHTTP port, so the served origin equals the generated masquerade origin; a regression test renders it.
- `split-hop-pilot.md` states that Node A's first deploy runs without the ingress listener and how to add it before the ingress phase.
- The disposable staging recipe states the operator-address rollback and its recovery.
