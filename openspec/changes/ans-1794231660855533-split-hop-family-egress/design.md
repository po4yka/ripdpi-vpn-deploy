## Context

`split-hop-ingress` marks new original IPv4 sockets of two fixed research UIDs in an owned `inet split_hop_ingress` table, policy-routes the mark into the B-initiated tunnel and SNATs to A's tunnel address; the canonical firewall mirrors the UID guard. Family recipient egress does not run under those UIDs: Xray and Hysteria send recipient traffic through the transport normalizer to the native direct gateway (`transport-gateway`), whose `freedom` outbound and DoH resolver open the upstream sockets. AmneziaWG traffic is forwarded and masqueraded on the uplink by the firewall.

## Goals / Non-Goals

- Goal: one selector routes every family recipient flow on Node A through Node B and fails closed.
- Goal: keep the research scope's behavior and both independent guards.
- Non-goal: Node B changes, a new tier, IPv6 through the tunnel, WARP or other direct-egress transports in family scope, live acceptance in this change.

## Decisions

- Select by UID for local egress and by input interface for forwarded AWG. The gateway and normalizer users are the only recipient egress identities in the protected generation; the normalizer is included so no resolver configuration can reach the uplink. Rejected: per-socket `SO_MARK` in the gateway (needs `CAP_NET_ADMIN`, which the gateway must not hold) and cgroup matching (unit cgroups are created after policy load).
- Resolve UIDs with `getent` at convergence. transport-egress allocates dynamic system UIDs; fixed UIDs would migrate existing nodes. The split-hop role runs after transport staging and refuses absent users; the firewall renders the users it finds, so a fresh host's first firewall publication carries only the research UIDs and the split-hop table supplies the boundary once its role runs.
- The firewall owns AWG forwarding and NAT on the tunnel interface (selected through `awg_forward_interface`), keeping its counters and destination deny lists; the split-hop table adds the prerouting mark, an IPv6 reject and a non-tunnel drop.
- IPv4 only: the tunnel's AllowedIPs are IPv4 and Node B's NAT is IPv4. The gateway therefore resolves and dials IPv4 so dual-stack names do not fail after SOCKS success is published.
- Loose `rp_filter` on the tunnel interface only (effective max(all, iface) = 2); MSS clamp to route MTU because rerouted sockets choose MSS from the uplink route.

## Contracts and ownership

- `ansible/group_vars/all.yml`: `vpn.split_hop_family_egress`.
- `roles/split-hop-ingress`: `policy.nft.j2`, `split-hop-ingress.conf.j2`, `tasks/enable.yml`, defaults `split_hop_ingress_family_users|uids|interfaces`.
- `roles/firewall`: `nftables.conf.j2`, `tasks/main.yml`, defaults `split_hop_ingress_family_users`, `firewall_split_hop_family_uids`.
- `roles/transport-egress/templates/gateway.json.j2`.
- `playbooks/site.yml` family guard.
- No secrets, Terraform or client contract change.

## Risks / Trade-offs

- Node B or tunnel loss stops all family transports on A → by design; the deploy-time transport canary and watchdog probes traverse the gateway and therefore the tunnel, so the outage is observed. Operators keep a second node for continuity.
- Recipient IPv6 destinations are unavailable in family scope → accepted; dual-stack names resolve to IPv4.
- Fresh-host first deploy: transport acceptance runs before the split-hop table exists, so its canary leaves A directly once → limited to the operator-owned canary URL before any client is enrolled.
- Double encapsulation for AWG reduces MTU → MSS clamp on tunnel egress; UDP payloads rely on the devices' configured MTU.

## Migration Plan

Forward: provision and enroll Node B, enable split-hop ingress/egress as today, then set `vpn.split_hop_family_egress: true` in Node A's host vars and run the normal dry-run and deploy. Rollback: set it false and converge A; the firewall restores uplink forwarding and the policy returns to the research scope. Gates: authorized dry-run, staging converge with recipient-observed source checks for Xray, Hysteria and AWG, and a stopped-tunnel leak check before any family host uses it.
