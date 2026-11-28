---
id: TFR-1795329107889572
title: Manage Porkbun DNS with a pinned OpenTofu root
kind: feature
status: doing
area: terraform
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: [TFR-1795328347526492, TFR-1795328481774241, ANS-1795328948145006]
spec_mode: required
openspec_change: tfr-1795329107889572-porkbun-dns-root-w6
created: 2026-11-22
updated: 2026-11-28
related_tasks: []
---

## Goal

DNS records of the fleet's managed Porkbun domains are managed by an OpenTofu root with a vetted pinned provider, encrypted state, a scope policy and keys limited per domain, permission and egress address.

## Acceptance criteria

- The provider vetting record and exact pin with lock hashes are committed.
- `make tf-test` and `make tf-policy-verify` cover the root and the scope policy.
- Authorized adoption applies exactly the reviewed imports with zero DNS changes, then produces an empty plan per domain.
