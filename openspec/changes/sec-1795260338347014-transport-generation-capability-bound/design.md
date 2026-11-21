## Context

The controller runs as root with `AmbientCapabilities=CAP_SETUID` and no bounding set. Its operations are: systemd unit control over D-Bus, UID and GID changes for frontend children, nftables restore through netlink after a reboot, and the WARP network namespace refresh.

## Goals / Non-Goals

Goals: the smallest bounding set under which every operation passes the native acceptance; a recorded reason for each capability.

Non-goals: running the controller as a non-root user, splitting the controller into several units, changing its operations beyond what the bound requires.

## Decisions

- Derive the set from the operations, then prove it on the native lanes; do not copy a set from another unit.
- Start from `CAP_SETUID`, `CAP_SETGID` and `CAP_NET_ADMIN`, and add any further capability only when a native test fails without it.
- Keep `User=root`, so file ownership of the state directory does not change.

## Contracts and ownership

The transport-egress role owns the unit. The frontend roles and the WARP namespace owner keep their units unchanged.

## Risks / Trade-offs

- A capability that only a rare path needs (reboot recovery, namespace refresh) can be missed by a short test; the staging run must include a reboot and a namespace refresh.
- `RestrictNamespaces=true` already limits namespace creation; the namespace refresh must stay inside what that permits.

## Migration Plan

Deploy to a disposable node first, reboot it, and check frontend recovery. Rollback removes the bounding set line.
