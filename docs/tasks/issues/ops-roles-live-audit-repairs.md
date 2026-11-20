---
id: OPS-1795165613781138
title: Close operations-role gaps from the 2026-11-20 fleet audit
kind: bug
status: review
area: operations
priority: high
risk: high
owner: Operations remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795165613781138-ops-roles-live-audit-repairs
created: 2026-11-20
updated: 2026-11-20
related_tasks: []
status_detail: Implementation and local checks complete; pull request open for CI and owner review.
---

## Goal

A wedged transport on any production node is recovered by the local watchdog without a restart of a transport that still serves clients, a backup or restore failure becomes visible within one drill cadence, and routine maintenance (security upgrades, the host audit, Tailscale logging) neither interrupts all nodes in one window nor sends node data to a vendor. Source: the read-only repository and live-node audit of 2026-11-20.

## Acceptance criteria

- The `vpn-p1-web` and `vpn-p2-udp` profiles enable the watchdog; a failed StatsService query alone requests no recovery; recovery stops after `kicks_per_outage_max` attempts in one outage; the unit has memory and CPU limits.
- The backup and restore-drill units have a start deadline, and the backup script syncs nothing when the remote path holds a different restic repository.
- The restore drill runs weekly; `make inspect` and the health adapter default treat restore evidence as stale after 15 days, and a 14-day-old drill is not stale.
- The inspection report states whether a reboot is pending, and the unattended-upgrade timer has a fixed per-host delay.
- tailscaled has log upload disabled, the Lynis collector disables the online version test, and runtime activation refuses after a bounded lock wait.
- A Tailscale version pin, a new offsite directory name, a Telegram relay proxy path and a pending-reboot metric stay out of scope.
