## Context

Node A marks forwarded device flows and new connections of the frontend UIDs with the split-hop fwmark. An `ip rule` sends marked traffic to the split-hop routing table, whose default route uses the WireGuard interface. `forward_guard` drops forwarded flows that leave by another interface, and `egress_guard` in postrouting drops frontend UID traffic that leaves by another interface. `PostDown` deletes the rule and flushes the table.

## Goals / Non-Goals

Goals: an immediate error for both traffic classes while the tunnel is down; no traffic on the direct uplink; a clean state after retirement.

Non-goals: automatic failover to the direct uplink, changes to Node B, changes to the fwmark or table numbers.

## Decisions

- The boot policy loader installs the `ip rule` and an `unreachable default` with the maximum metric. The tunnel's own default route shadows it and disappears with the device, so marked traffic finds an error route however the tunnel stopped (stop, failed start, deleted device). `PostDown` is removed: a hook that only runs on a clean stop cannot hold this state.
- Add an output-hook reject chain (`tunnel_down`, priority `mangle - 1`) for new IPv4 originals of the marked frontend UIDs to non-local destinations, because postrouting cannot reject and a local `connect` ignores the reroute error. The policy file loads it; the role-owned `wg-quick@` drop-in flushes it after start (`ExecStartPost`) and reloads the policy after stop (`ExecStopPost`). The drop-in, not `PostUp`, owns this, because a loader restart propagates to the tunnel through `Requires=` and can start it under the previous tunnel configuration.
- Keep both existing guards unchanged as the last boundary.

## Contracts and ownership

The split-hop ingress role owns the rule, the table and the policy ruleset. The fwmark and table values stay in its defaults.

## Risks / Trade-offs

- A kept rule with an unreachable route also blocks marked traffic after an operator stops the tunnel on purpose; that is the intended fail-closed behaviour, and retirement is the way to remove it.
- The output reject must follow the interface state; a stale state can reject while the tunnel is up, so the acceptance must test both directions.
- The kernel rate-limits ICMP errors from the error route, so a device opening many flows at once can see some of them wait for a SYN retransmit.
- Only TCP connects fail at once locally; unconnected UDP sockets ignore the ICMP error, and established flows are not covered.

## Migration Plan

The next convergence installs the new `PostDown` and ruleset. Rollback restores the previous templates; the guards keep traffic contained either way.
