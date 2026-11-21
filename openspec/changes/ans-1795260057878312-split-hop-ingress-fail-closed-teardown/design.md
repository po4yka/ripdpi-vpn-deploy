## Context

Node A marks forwarded device flows and new connections of the frontend UIDs with the split-hop fwmark. An `ip rule` sends marked traffic to the split-hop routing table, whose default route uses the WireGuard interface. `forward_guard` drops forwarded flows that leave by another interface, and `egress_guard` in postrouting drops frontend UID traffic that leaves by another interface. `PostDown` deletes the rule and flushes the table.

## Goals / Non-Goals

Goals: an immediate error for both traffic classes while the tunnel is down; no traffic on the direct uplink; a clean state after retirement.

Non-goals: automatic failover to the direct uplink, changes to Node B, changes to the fwmark or table numbers.

## Decisions

- Keep the `ip rule` and replace the table content with `unreachable default` in `PostDown`, so marked traffic finds an error route instead of the main table.
- Add an output-hook reject for marked frontend UID connections while the WireGuard interface is absent, because postrouting cannot reject and a local `connect` ignores the reroute error.
- Keep both existing guards unchanged as the last boundary.

## Contracts and ownership

The split-hop ingress role owns the rule, the table and the policy ruleset. The fwmark and table values stay in its defaults.

## Risks / Trade-offs

- A kept rule with an unreachable route also blocks marked traffic after an operator stops the tunnel on purpose; that is the intended fail-closed behaviour, and retirement is the way to remove it.
- The output reject must follow the interface state; a stale state can reject while the tunnel is up, so the acceptance must test both directions.

## Migration Plan

The next convergence installs the new `PostDown` and ruleset. Rollback restores the previous templates; the guards keep traffic contained either way.
