# Change: Close UDP transport, firewall and split-hop gaps from the fleet audit

Task ID: `ANS-1795163654691828`

## Why

A read-only audit of the repository and of the live nodes on 2026-11-20 found properties that let a network observer or an active prober separate the UDP transport node from an ordinary host, and resource limits that the node inherited from its memory size. The node answered HTTP/3 on UDP/443 while TCP/443 and TCP/80 were closed. Hysteria sent at a fixed rate into UDP policing. Connection tracking held 7680 entries on a node that does NAT for AmneziaWG. The forward chain had no TCP MSS clamp, and the tunnel MTU default of 1420 needs a full 1500-byte path. Production admission refused the published AmneziaWG junk and padding set only when all five values matched. The cohort fingerprint of a parameter set without `wire_profile` was not the contract value. Split-hop egress had a fixed uplink name and a fixed peer port, forwarded to private destinations, and loaded its policy from an unsandboxed unit.

## What Changes

- The Hysteria role can serve its masquerade site over TCP/443, and over TCP/80 when native ACME is off. The `vpn-p2-udp` profile enables this. The listener manifest names the ports `hysteria-masquerade`.
- **BREAKING** for `vpn-p2-udp` nodes: the deploy refuses until the provider `public_listeners` contract carries the new TCP entries.
- The Hysteria congestion profile has a profile-level default. `vpn-p2-udp` sets `bbr-conservative`; a profile stated in the secrets document still wins.
- The baseline sysctl policy sets the connection tracking table size, its bucket count and both UDP timeouts, loads `nf_conntrack` before the policy is applied, and raises `fs.file-max` to 2097152.
- The firewall clamps the TCP MSS of forwarded AmneziaWG connections to the instance MTU, accepts DHCPv4 replies on the IPv4 uplink, and drops split-hop egress traffic to private and metadata destinations. The live listener verifier admits the scoped DHCPv4 rule.
- The AmneziaWG MTU default is 1280. The client bundle carries the resolved value, and its accepted range does not change.
- **BREAKING** for a production instance that kept part of the published set: admission refuses an instance that has the junk count and bounds, or both padding sizes, of that set.
- The cohort fingerprint uses the contract constant for an absent `wire_profile` and refuses any other absent value. Its output for a complete parameter set does not change.
- Split-hop egress resolves an empty uplink to the IPv4 default-route interface and an empty peer port to the ingress listen port. Its policy loader has the ingress loader's sandbox and stays active after exit.
- `awg-quick@.service` gets `MemoryDenyWriteExecute` and the `@system-service` system call filter.

## Capabilities

### New Capabilities

- `network/udp-node-transport-hardening`: public listener agreement between TCP and UDP on the UDP transport node, congestion default, connection tracking budget, tunnel MTU and MSS behaviour, DHCPv4 reply scope, split-hop egress defaults and destination boundary, unit sandboxing, and AmneziaWG shape and fingerprint admission.

### Modified Capabilities

- None

## Impact

- Ansible roles `hysteria`, `amneziawg`, `firewall`, `baseline`, `split-hop-egress`; `ansible/group_vars/vpn-p2-udp.yml`; `ansible/templates/listener-manifest.json.j2`.
- Scripts `transport_semantics.py`, `ripdpi_cohort_fingerprint.py`, `verify-public-listeners.py`, `observability-contract.py` (one listener name).
- Terraform: no file changes. The operator adds `hysteria-masquerade` entries to `public_listeners` of each `vpn-p2-udp` node and applies before the next deploy.
- Runtime effect at the next deployment of a UDP node: new TCP listeners, BBR congestion control, a tunnel MTU of 1280 unless the instance states another value, new forward-chain rules and a larger connection tracking table.
- Client bundle contract, secrets schema and `vpnd`: no change. Device configurations issued before the MTU change keep working and take the new MTU when they are redelivered.
