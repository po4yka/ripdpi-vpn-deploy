# Management route stalls on the relayed Tailnet path — 2026-11-27

> **Status:** Research · **Type:** research · **Tier:** — · **Reviewed:** 2026-11-27

Why the operator machine reaches production nodes only through a DERP relay, what ended the timed previews of 2026-11-26 and 2026-11-27, and how the controller keeps a preview or deploy alive on that route. Recorded for task `OPS-1795702284251279`; the controller change is task `SCR-1795774108061951`.

## Evidence

- Operator side: `tailscale netcheck` and `tailscale status --json` on the operator machine, and the Tailscale client's unified log. The client keeps its log for about ten hours, so it covers 2026-11-27 only.
- Node side: the `tailscaled` journal of node-b for 13:15 to 14:10 UTC on 2026-11-26, read with `journalctl` over the Tailnet SSH route. The split-hop B journal was not read: the operator's `known_hosts` holds no pin for its Tailnet address, and the session did not accept an unpinned key.
- A 60-minute `tailscale ping` probe to node-a and node-b on 2026-11-27, with the operator's home-region changes from the client log for the same hour.
- Run outcomes: the controller receipts and age-encrypted logs of the timed previews in [the preview cost research](preview-cost-2026-11.md), and the two node-a previews of 2026-11-27.
- Code: `ansible/roles/firewall/templates/nftables.conf.j2` and `scripts/deploy-controller.py` at `75cf136bd`.

## Why no direct path forms

All six production peers in the Tailnet were relayed (`CurAddr` empty) when this research ran. Two conditions together keep them relayed:

| Side | Observation | Effect |
|---|---|---|
| Operator | `MappingVariesByDestIP: true`, no UPnP, NAT-PMP or PCP port mapping, no IPv6, private gateway address | The operator's NAT gives each destination its own source port, so the port that a node learns through STUN is not the port that the operator uses towards that node. |
| Node | The input chain has `policy drop` and no accept for UDP 41641; Tailscale UDP enters only through `ct state established,related`. Strict output allows source port 41641 and STUN port 3478. | A node accepts the operator's UDP only after the node has sent to the same address and port first, which it cannot do when it does not know that port. |

Hole punching succeeds when at least one side keeps one external port for all destinations or accepts unsolicited UDP. Here neither does, so every peer stays on DERP. Relay policy is not the cause: the client chose its home region by latency, and nothing in the tailnet policy forces relaying.

A direct path needs one of these changes:

- **Admit inbound UDP 41641 on each node** (nftables input and the provider firewall). The operator's packets would then open the flow from its side. Security effect: the node address carries plain WireGuard flows from the operator, a protocol signature that the node otherwise does not show, and the public listener contract gains a UDP port. tailscaled answers only authenticated peers, so a scan sees no reply either way, but the traffic itself is visible to a passive classifier on the node's path. Not recommended under the active fingerprinting threat model.
- **Move the operator to a network with endpoint-independent mapping or IPv6.** No node change and no new exposure; outside the repository's control.
- **Run the controller from a host with a public address** (the `EPC-1795327697650892` direction). The controller host, not the nodes, would then need its own reachable UDP port.

## What ended the runs

The node-b journal shows the mechanism. The operator's home DERP region changes often: on 2026-11-27 the client log recorded 99 home-region changes and 144 changes of its external endpoints between 02:30 and 13:50 local time, because five regions were within 6 ms of each other (95 to 101 ms). After such a change, a node keeps sending to the operator through the previous region until it learns the new home region; that region answers `derp-N does not know about peer`, and the packet is lost. With no direct path there is no other route for the reply.

| Run (UTC) | Node-side window without a reply path | Controller outcome |
|---|---|---|
| 2026-11-26 13:07 previews of node-b and split-hop B | 13:22:04 to 13:24:01 (117 s): node-b sends to the operator through derp-22, which does not know the operator, until it connects derp-4 | Both previews lost their Tailnet SSH session within 6 s of each other: split-hop B at 13:23:21 (`Data could not be sent`), node-b at 13:23:27 (`connect ... port 22: Operation timed out`). The shared master gives up after 120 s of silence. |
| 2026-11-26 13:25 preview of node-b (base2) | 13:47:44 to at least 13:49:20 (96 s and more): derp-4 does not know the operator | The preview lost its session at 13:49:28. |
| 2026-11-26 14:06 preview of node-b (`c7576d564`) | From 14:06:42: node-b connects derp-22 and derp-4 for the operator, and derp-4 does not know the operator | The readiness probe (`ssh ... true`, 15 s) failed with `SSH session timeout` at 14:06:42. |
| 2026-11-27 08:47 preview of node-a | Operator side: endpoints changed at 08:47:26; at 08:47:41 the client needs node-a's home region derp-28, which it had not used for 12 h 38 min; the first connection attempt ends with `context deadline exceeded` and the region connects at 08:47:49 | The readiness probe failed with `SSH session timeout`; the controller had not yet run any `tailscale ping`, which would have connected the region first. |

A 60-minute probe on 2026-11-27 (10:03 to 11:03 UTC) sent one `tailscale ping` to node-a and to node-b every 2 s with a 3 s timeout:

| Node | Probes | Replies | Direct replies | Median / p95 round trip | Longest gap |
|---|---|---|---|---|---|
| node-a | 1775 | 1773 | 0 | 147 / 233 ms | 12 s |
| node-b | 1775 | 1774 | 0 | 113 / 201 ms | 11 s |

The operator's home region changed twice in that hour, against 7 to 14 times an hour earlier that day. Both nodes lost their replies at the same time, 10:38:55 to 10:39:06, 19 s after one of those changes. The probe therefore reproduces the mechanism, but not the 96 to 117 s windows of 2026-11-26: how long a gap lasts depends on when the node learns the new home region, which this probe does not control.

The machine did not sleep during these runs: the power log of 2026-11-26 and 2026-11-27 holds no sleep or wake event. The two 2026-11-26 sessions that failed together were on different nodes, which also points to the operator side.

## Decisions

- **`dry-run` measures the management route at start, as `deploy` does.** A preview over a route that cannot carry it should stop in seconds, not after 20 minutes. Both modes also send one warm-up probe that waits up to 30 s before the readiness probe, so a cold relay region is connected before the first SSH command. This changes deployment lifecycle behaviour and is task `SCR-1795774108061951` (`spec_mode: required`, change `scr-1795774108061951-management-route-warmup`).
- **Check mode does not get a longer stall budget than a deploy; both get a longer one.** The observed reply gaps were 96 to 117 s against a 120 s budget. Waiting longer is safe in both modes: when the SSH client gives up, the remote command loses its session in the middle of a task, which is worse in a deploy than waiting. The same change raises the shared master to `ServerAliveCountMax=20` (300 s) in both modes. Ansible SSH retries stay disabled in both, because a retry after a lost connection can run a protected-transaction task twice.
- **No inbound UDP 41641 on nodes.** The direct path would remove the reply gaps but adds a plain WireGuard signature to every node address.

## Gaps

- The operator-side client log for 2026-11-26 had already rotated, so the 2026-11-26 home-region changes are seen only from node-b. The node-b journal names the regions that the node tried, not the moment the operator changed its home region.
- The split-hop B journal was not read (no pinned host key for its Tailnet address).
- The 300 s budget covers the observed gaps with margin; it is not derived from a documented upper bound on how long a peer can keep a stale home region.
