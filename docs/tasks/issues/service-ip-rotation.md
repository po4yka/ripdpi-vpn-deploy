---
id: OPS-1795856574795376
title: Rotate a node's client-facing IPv4 without replacing the server
kind: feature
status: review
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795856574795376-service-ip-rotation
created: 2026-11-28
updated: 2026-11-28
related_tasks: []
status_detail: Source and protected-main evidence passed; dry-run, staging and client evidence moved to OPS-1795867688528839
---

## Goal

An operator can give an existing node a new client-facing IPv4 from the same provider, move every device to it through the unchanged subscription URL and retire the old address, without replacing the server or changing its SSH, Tailnet or device credentials.

## Acceptance criteria

- Every provider root attaches at most two named movable IPv4 generations to the existing server and exports `service_ipv4` and `service_ipv4_addresses`; `server_ipv4` stays the primary address (mock-provider tests).
- Inventory publishes `vpn_service_address` (client endpoint), `vpn_host_address` (host identity) and `vpn_service_addresses`, and refuses missing or inconsistent outputs (unit tests).
- Host identity consumers use the host address; client-path consumers use the service address (unit tests).
- The `baseline` role owns, repairs and retires the guest `/32` of each service address (Molecule).
- The honeypot secondary-IP policy does not refuse service addresses (policy tests).
- `docs/how-to/rotate-service-ip.md` covers attach, DNS move, device refresh, retirement and rollback.
- Staging evidence: one rotation on a disposable node with a refreshed client before production use.
