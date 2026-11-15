---
id: SEC-1794729595622909
title: Measure fleet-wide transport signatures before changing defaults
kind: research
status: done
area: security
priority: medium
risk: standard
owner: Security remediation
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-15
updated: 2026-11-15
spec_reason: research-only
related_tasks: []
closed_at: "2026-11-15T13:07:28Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "docs/research/fleet-transport-signatures-2026-11.md merged in 180049e1 (PR 609): seven fleet-wide signatures measured on loopback, each with method, result and verdict; no verdict is change-the-default, so no follow-up task is filed; the Salamander row of the threat model is corrected in the same commit. The PR checks passed on a tree equal to the merged commit."
---

## Goal

The 2026-11-15 repository audit listed network signatures that are the same on every node and that static review cannot rank. This task measures them in an isolated lab and records which defaults to change. Each accepted change becomes its own spec-required task.

Signatures to measure:

- Split-hop and cascade tunnels use plain WireGuard on fixed ports with a fixed keepalive (decision 0003).
- Hysteria runs without Salamander by default, while `docs/explanation/threat-model.md` names Salamander as the protection; the default bandwidth profile sends at one fixed rate on every node.
- The XHTTP inbound has no Vision flow, so the inner TLS handshake can show through the outer TLS record sizes.
- The nginx TLS profile is the same on every node: TLS 1.3 only, one key-exchange group, no session tickets, and an HSTS header with a zero age on non-443 ports.
- The default public port set and the silent drop on every other port.
- `net.ipv4.tcp_fastopen = 3` on a node whose REALITY target can answer differently.
- The watchdog fetches one shared canary URL on a fleet-wide timer, and the standard client artifact tests every outbound to one address at one fixed interval (`REQ-TMD-CLIENT-CADENCE`).

## Acceptance criteria

- A page under `docs/research/` gives, for each signature above, the capture or probe method, the observed result and a verdict: change the default, keep it with a reason, or measure on a filtered path.
- Lab captures use only local or disposable endpoints; the page holds no node address, hostname or network label.
- The page corrects or confirms the Salamander statement in `docs/explanation/threat-model.md`, and that file is updated in the same change when the statement is wrong.
- Each "change the default" verdict has a filed portfolio task with `spec_mode: required`.
