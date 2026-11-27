---
id: OPS-1795702284251279
title: Keep full-graph previews alive through relayed Tailnet stalls
kind: research
status: done
area: operations
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-26
updated: 2026-11-27
spec_reason: research-only
related_tasks: []
status_detail: "Cause named from evidence: operator NAT with destination-dependent mapping plus node input policy keep every peer on DERP; node-b journal ties the 2026-11-26 stalls to operator home-region changes; controller change is SCR-1795774108061951"
closed_at: "2026-11-27T11:33:40Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "docs/research/management-route-stalls-2026-11.md: no direct path because the operator NAT maps each destination to its own port and node input accepts Tailscale UDP only for established flows; node-b tailscaled journal ties the 2026-11-26 stalls (96 to 117 s) to operator home-region changes, and the 2026-11-27 readiness timeout to a cold relay region; decisions and follow-up task SCR-1795774108061951 (spec_mode required)."
---

## Goal

On 2026-11-26 the management route from the operator machine to every production node went through a DERP relay, with a median RTT of 120 to 370 ms, and stalled several times for longer than the SSH keepalive budget (15 s × 8). The stalls ended three of four timed full-graph previews and one deploy ([the preview cost research](../../research/preview-cost-2026-11.md)), each after 15 to 25 minutes of work. This research finds the cause of the stalls and of the missing direct paths, and decides how a preview or deploy avoids losing a long run to one stall, without a retry that can run a protected task twice.

## Acceptance criteria

- The cause of the missing direct Tailnet path to each node is named from evidence (operator-side NAT, node firewall, or relay policy), with the change that would allow a direct path and its security effect on the node's exposure.
- The stall events are correlated with operator-side network events (address changes, relay changes, sleep) from logs with times.
- A decision states whether `dry-run` measures the management route at start as `deploy` does, and whether check mode may tolerate a longer stall than a deploy; a change to deployment lifecycle behaviour gets its own task with `spec_mode: required`.
