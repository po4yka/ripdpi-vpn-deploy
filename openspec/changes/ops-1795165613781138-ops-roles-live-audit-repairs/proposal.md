# Change: Close operations-role gaps from the 2026-11-20 fleet audit

Task ID: `OPS-1795165613781138`

## Why

A read-only audit of the repository and of the live nodes on 2026-11-20 found gaps in the roles that supervise, back up and patch a node. The XHTTP node and the UDP node ran no watchdog, so a wedged nginx, Hysteria or AmneziaWG had no local recovery. The watchdog itself could restart a serving Xray after a failed loopback API query, repeated a recovery that did not help three times each hour without limit, and had no memory or CPU bound. The backup and restore-drill units had no start deadline, and a recreated node could replace its own offsite history with a new empty repository. `make inspect` reported every node `stale` 36 hours after each monthly restore drill. Unattended security upgrades ran on all nodes in one window, a pending reboot was visible on no surface, tailscaled uploaded client logs, the Lynis audit made a vendor DNS query, and a runtime activation could wait for a lock without limit.

## What Changes

- The `vpn-p1-web` and `vpn-p2-udp` profiles enable the watchdog.
- A failed Xray StatsService query alone no longer selects Xray for recovery.
- The watchdog stops recovery after `kicks_per_outage_max` attempts in one outage and only alerts until a run selects no unit.
- The watchdog unit has memory and CPU limits, and its timer has a 150-second random delay.
- The backup and restore-drill units have a one-hour start deadline.
- The backup script refuses to sync when the remote path holds a different restic repository.
- The restore drill runs weekly. Restore evidence is stale after 15 days in `make inspect` and in the health adapter, and the snapshot age is measured against that window.
- The inspection report has a `reboot_required` field.
- The unattended-upgrade timer has a fixed delay of up to 12 hours that differs between hosts.
- tailscaled runs with log upload disabled.
- The Lynis collector disables the scanner's online version test.
- The runtime-release activation lock has a ten-minute wait limit.

**BREAKING** for operators: `vpn-p1-web` needs a `watchdog` entry in `xray.clients`, `vpn-p2-udp` needs a `watchdog` entry in `hysteria.clients`, and both need `watchdog_secrets.reality_probe_url`; deployment refuses without them. The inspection report gains a required field.

## Capabilities

### New Capabilities

- `operations/ops-roles-audit-repairs`: recovery, backup, patch-window and local-audit properties that the operations roles must hold on a managed node.

### Modified Capabilities

- None

## Impact

- Ansible roles `watchdog`, `backup`, `package_updates`, `tailnet-management`, `security_audit`, `runtime-release`; the default restore window in `observability_agent`; group vars of two profiles; `scripts/fleet_inspection.py`; their tests, snapshots and notes.
- Runtime effect at the next deployment: the watchdog timer appears on two nodes, the drill timer becomes weekly, the upgrade timer moves, and tailscaled takes the log setting at its next start.
- No Terraform, cloud-init, secret schema, `vpnd` or client change.
