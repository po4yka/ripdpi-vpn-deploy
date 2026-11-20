## Context

The Hysteria role renders one YAML configuration and requires `hysteria.masquerade_url` to equal `public_site_canonical_url`. `site.yml` compares the rendered listener manifest with the provider contract by name, protocol and port before any role runs. The firewall role accepts public ports only through that contract. The baseline role applies `/etc/sysctl.d/90-vpn.conf` on every converge with a helper that lets only lines marked `-` fail. AmneziaWG MTU resolves from instance, cohort and role default, and the same resolved value reaches the server configuration and the client bundle.

## Goals / Non-Goals

- Goal: a UDP transport node deployed from this revision answers on TCP where it answers on UDP, does not send at a fixed rate, has an explicit connection tracking budget, and carries TCP through the tunnel without fragmentation on a 1360-byte path.
- Goal: split-hop egress works on provider images that do not name the uplink `eth0`, and cannot forward to private destinations.
- Non-goal: a node-local masquerade origin for a node without a web frontend. It needs the `file` masquerade type and a published site tree, which belongs with the operator site bundle of `ANS-1795162466557355`.
- Non-goal: a per-source connection limit or an address-family restriction on public listener accepts, a narrower capability set for the transport egress generation controller, a fail-fast split-hop ingress `PostDown`, and a change to the `narrow-junk-sequential` cohort file. The pull request records the reason for each.
- Non-goal: any Terraform file change and any live action.

## Decisions

- Serve the masquerade over TCP from Hysteria itself (`listenHTTPS`, `listenHTTP`, `forceHTTPS`) behind one role input. Rejected: enabling nginx on the UDP node, which adds a second TLS identity owner and a transport-capable role to a node that needs neither.
- With native ACME, do not bind TCP/80. CertMagic skips a port that is already bound and expects the existing listener to answer HTTP-01; the masquerade handler does not, so certificate renewal would fail. TCP/80 stays the transient `hysteria-acme` allowance. Rejected: TLS-ALPN-01, which has the same conflict on TCP/443.
- Name the listeners `hysteria-masquerade` in the manifest so that the existing contract comparison forces the provider firewall and the node firewall to agree. Rejected: opening the ports from a role variable, which the firewall role forbids.
- Put the congestion default in a role input that the profile overrides, with the secrets value first. Rejected: changing the meaning of an absent `hysteria.resource_profile` everywhere, because client emitters, liveness profiles and admission read that default from the secrets document alone. Consequence: client exports keep bandwidth hints until the operator states the profile; the server ignores them and signals automatic rate selection.
- Add connection tracking keys as optional lines and load the module in the role and at boot. Rejected: mandatory keys, because a container has no module and the keys do not exist before the first firewall load on a fresh host.
- Clamp with fixed sizes for packets from the tunnel and with the route MTU for packets to it. A fixed size is needed for the first direction because the route MTU there is the uplink's. The kernel does not raise an MSS, so the rules are safe for a device with a smaller MTU.
- Lower the MTU default to 1280 for every profile. AmneziaWG runs only on UDP-type nodes, 1280 is one of the two measured endpoints of the supported range, and the clamp keeps devices with an older configuration working.
- Resolve the split-hop uplink and peer port in the templates and the policy shape check, with empty defaults. Rejected: Jinja expressions inside the nested defaults map, which the snapshot renderer does not evaluate.
- Refuse the published junk triple or padding pair separately. Each one is observable on its own: the junk packet sizes, and the handshake initiation and response sizes.

## Contracts and ownership

- Provider contract: Terraform `public_listeners` gains `hysteria-masquerade` TCP entries per `vpn-p2-udp` node. Owner: operator. The deploy fails closed until it matches.
- Observability contract: `hysteria-masquerade` joins the accepted VPN listener names.
- Client bundle contract: unchanged. `mtu` stays within 1280 to 1420 and the fingerprint algorithm output for complete input is unchanged; the paired golden file is not edited.
- One writer for all paths in the task's ownership section.

## Risks / Trade-offs

- The first deploy of a UDP node after this change refuses until the provider contract is updated. This is the intended order: provider firewall first, then the node.
- With native ACME, TCP/80 answers only during a challenge. TCP/443 and UDP/443 agree, which removes the single-comparison signal; a closed TCP/80 beside an open TCP/443 is common.
- The masquerade origin of a node without a web frontend is still another host. The role refuses only the self-referencing origin.
- A tunnel MTU of 1280 costs about ten percent of payload per packet on an unconstrained path. An instance can state up to 1420.
- A production instance that changed only part of the published junk and padding set is refused at the next deploy and needs generated values and redelivered device configurations.
- Connection tracking at the default budget can use about 42 MiB on the smallest node when full.

## Migration Plan

1. Operator: add the `hysteria-masquerade` entries to `public_listeners` of each UDP node and apply Terraform.
2. Operator: state `hysteria.resource_profile` in the secrets document.
3. Dry-run and deploy each UDP node under separate authorization; run `verify`, `security-verify` and `smoke-test`.
4. Rollback: revert the commit and redeploy. The new TCP listeners, forward rules and sysctl values leave with the rendered files; the provider entries can stay or be removed after the node no longer listens.
