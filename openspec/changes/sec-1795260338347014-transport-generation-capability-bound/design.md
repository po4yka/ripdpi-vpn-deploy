## Context

The controller runs as root with `AmbientCapabilities=CAP_SETUID` and no bounding set. The unit runs only `generation.py run`. Its operations are: systemd unit control through `systemctl`, normalizer journal reads through `journalctl`, `/proc` and cgroup reads, root-owned state file writes, UID and GID changes for the readiness child, and the kill of that demoted child at its deadline. The nftables restore after a reboot and the WARP namespace refresh run in other units: `generation.py prepare` in the normalizer's privileged (`+`) ExecStartPre, and the refresh in `ripdpi-warp-refresh.service`, which the loop only starts through `systemctl`.

## Goals / Non-Goals

Goals: the smallest bounding set under which every operation passes the native acceptance; a recorded reason for each capability.

Non-goals: running the controller as a non-root user, splitting the controller into several units, changing its operations beyond what the bound requires.

## Decisions

- Derive the set from the operations, then prove it on the native lanes; do not copy a set from another unit.
- The set is `CAP_SETUID`, `CAP_SETGID` and `CAP_KILL`. `setgroups`/`setgid` and `setuid` in the readiness child's pre-exec drop need the first two; `subprocess.run` kills a timed-out child that no longer shares the controller's UID, which needs `CAP_KILL`. Root-owned files, the systemd private socket and the journal need UID 0 only. `CAP_NET_ADMIN` is not in the set, because no netlink operation runs in this unit. Add a capability only when a native test fails without it.
- Keep `User=root`, so file ownership of the state directory does not change.

## Contracts and ownership

The transport-egress role owns the unit. The frontend roles and the WARP namespace owner keep their units unchanged.

## Risks / Trade-offs

- A capability that only a rare path needs (reboot recovery, namespace refresh) can be missed by a short test; the staging run must include a reboot and a namespace refresh.
- A later change that moves policy restore or the namespace refresh into the `run` loop must add its capability; the role note records this.

## Migration Plan

Deploy to a disposable node first, reboot it, and check frontend recovery. Rollback removes the bounding set line.
