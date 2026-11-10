---
id: ANS-1794322927427537
title: Add split-hop staging cohort profiles for Node A and Node B
kind: feature
status: doing
area: ansible
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1794322927427537-split-hop-staging-cohort-profiles
created: 2026-11-10
updated: 2026-11-10
related_tasks: []
---

## Goal

The canonical deployment controller can stage both split-hop nodes for `ANS-1794231660855533`: Node B through a listener-free egress cohort, Node A through ingress and family-egress cohorts that keep every `device-full-staging` transport.

## Acceptance criteria

- `vpn-split-hop-egress-staging`, `vpn-split-hop-ingress-staging` and `vpn-split-hop-family-egress-staging` exist outside `family_profiles` with same-file research allowlists, and `scripts/check-deploy-profile.py` passes.
- The no-listener promotion test admits the shipped Node B profile; a contract test pins both Node A profiles to `device-full-staging` plus their split-hop toggles.
- The split-hop pilot guide no longer directs operators to host vars and states the fresh Node A cohort sequence.
- A staging dry-run of each node with its cohort is recorded under `ANS-1794231660855533`.
