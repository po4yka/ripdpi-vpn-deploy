# Change: Route family transport egress through the split-hop exit node

Task ID: `ANS-1794231660855533`

## Why

Every family transport on a node (P0/P1 Xray, P2 Hysteria2, P2 AmneziaWG) leaves for the recipient from the same public IPv4 that clients connect to. Two independent observers can bind that address to proxy use without reading the payload: application telemetry that reports the egress address seen while a device VPN is active, and a flow-level classifier that scores one IP for both accepting and initiating flows (`docs/decisions/0003-split-hop-relay-topology.md`). Either burns the single ingress address, which carries all family tiers at once. The split-hop pair already separates the roles, but Node A routes only two research runtime UIDs through Node B.

## What Changes

- New opt-in Node A selector `vpn.split_hop_family_egress` (default `false`). With `enable_split_hop_ingress`, original-direction IPv4 flows of the transport normalizer and direct gateway users (all Xray and Hysteria recipient egress, including DoH resolution) and forwarded AmneziaWG originals route through the B-initiated tunnel. IPv6 originals from those sources are refused.
- The canonical firewall moves AmneziaWG forwarding and NAT from the uplink onto the tunnel and extends the shared split-hop guard to the family UIDs, so a stopped tunnel or missing split-hop table fails closed instead of leaking through the uplink.
- The direct gateway resolves and dials IPv4 only in family scope.
- The tunnel interface uses loose reverse-path filtering so tunnel replies survive baseline's strict `rp_filter`; this also repairs the existing research scope. Tunnel-bound SYNs are MSS-clamped to the route MTU.
- `site.yml` refuses family scope without the ingress responder and while transports that own direct egress are enabled (Naive, Snell, DNS-Morph, Hysteria realm, WARP, split-hop egress on the same host).
- BREAKING (opt-in only): in family scope, recipient IPv6 destinations fail and every family transport stops carrying traffic while Node B or the tunnel is down.

## Capabilities

### New Capabilities

- `network/split-hop-family-egress`: Node A family recipient egress leaves only through the B-initiated tunnel and fails closed.

### Modified Capabilities

- None.

## Impact

- Ansible: `split-hop-ingress` (policy, configuration, identity resolution), `firewall` (forward, NAT, shared guard), `transport-egress` (gateway address family), `playbooks/site.yml` guard, `group_vars/all.yml`.
- No Terraform, secrets schema, vpnd or client contract change. Clients keep their existing profiles; Node B needs no change.
- Tier stays RESEARCH; live use still requires `allow_research_roles` and a provisioned Node B.
