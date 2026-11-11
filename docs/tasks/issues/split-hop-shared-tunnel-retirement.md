---
id: ANS-1794373808075617
title: Keep the shared split-hop tunnel when the paired role is enabled
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

Both split-hop roles use the `shop0` tunnel, and each role's `disable.yml` retired `wg-quick@shop0` and `/etc/wireguard/shop0.conf`. Observed on staging Node B: the disabled ingress role stopped the egress tunnel and deleted its config in the same run that started it, and the `Restart wg-quick` handler then failed with "/etc/wireguard/shop0.conf does not exist". On Node A the disabled egress role would flap the ingress tunnel on every deploy.

## Acceptance criteria

- A role's retirement leaves `wg-quick@shop0` and `/etc/wireguard/shop0.conf` alone when the paired role is enabled on the host, and still retires them when it is not (including subscription-only hosts).
- Each role still retires its own policy unit, nft file and drop-in.
- A regression test evaluates the real retirement lists and fails without the fix.
