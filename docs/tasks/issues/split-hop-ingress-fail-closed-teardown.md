---
id: ANS-1795260057878312
title: Make split-hop ingress flows fail fast after the tunnel stops
kind: feature
status: doing
area: ansible
priority: medium
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795260057878312-split-hop-ingress-fail-closed-teardown
created: 2026-11-21
updated: 2026-11-21
related_tasks: [ANS-1795163654691828]
---

## Goal

When the split-hop tunnel on Node A stops, device flows and local frontend connections that the policy sends to Node B fail at once with an error instead of a timeout, and still never leave through the direct uplink. Follow-up of the fleet audit change `ANS-1795163654691828`, which declined this fix because it changes the ingress policy tables and needs a live pair to test.

## Acceptance criteria

- With the tunnel down, a forwarded device flow gets an ICMP unreachable error and no packet leaves by the direct uplink.
- With the tunnel down, a marked frontend `connect` fails within one second.
- Retirement removes the split-hop rule, table content and reject rule.
- A disposable Node A and Node B pair shows all three.
