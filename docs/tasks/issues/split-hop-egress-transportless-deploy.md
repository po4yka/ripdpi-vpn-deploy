---
id: SCR-1794283047368821
title: Deploy a split-hop egress node that publishes no client listener
kind: bug
status: backlog
area: scripts
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1794283047368821-split-hop-egress-transportless-deploy
created: 2026-11-10
updated: 2026-11-10
related_tasks: []
---

## Goal

`make deploy` converges a split-hop egress Node B that publishes no client listener, so the split-hop pilot and the family egress acceptance (`ANS-1794231660855533`) can run. No host that publishes, or may publish, a client listener can skip the SSH promotion sentinel proof.

## Acceptance criteria

- A `no-public-listener` promotion document is admitted only for a host whose own inventory row records an empty provider listener contract, with no group-wide, override or secrets shadow, and whose effective `vpn` is explicitly egress-only; every other host refuses before SSH.
- The SSH baseline transaction for that kind binds the exact target, keeps fresh status and SFTP on every management transport, and runs no sentinel proof.
- The UpCloud root plans `node_purpose = "split-hop-egress"` with no listener and refuses a public listener for it.
- Unit and Terraform tests cover admission, refusal, the transaction branch and the provider preconditions.
