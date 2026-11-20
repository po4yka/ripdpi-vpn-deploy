## Context

The watchdog renders one shell script that probes each enabled transport and keeps a six-key budget file, which the observability health adapter parses with an exact key set. The backup role renders a daily backup script and a restore drill; the health adapter and `scripts/fleet_inspection.py` each hold their own freshness windows. See `proposal.md` for the audit findings.

## Goals / Non-Goals

- Goal: the properties in `operations/ops-roles-audit-repairs` hold after a normal deployment, with no new secret schema key.
- Non-goal: an apt version pin or an auto-update setting for Tailscale (the owner chose automatic updates on 2026-11-16, `sec-1794807596362904-baseline-live-audit-hardening`), a new name for the offsite replica directory, a proxy path for the Telegram relay, a pending-reboot metric in the telemetry allowlist, and any live action.

## Decisions

- Keep the outage counter in `<state_file>.outage`, not as a seventh budget key. Rejected: a new key, because the health adapter refuses any budget file with another key set and is deployed by a separate lifecycle, so a node would report failed watchdog evidence between the two deployments.
- Let a failed StatsService query select Xray only together with a failed authenticated round trip. Rejected: a diagnostic-only check, because a wedged Xray that still holds its listener then has no recovery path: listener and unit checks pass, and a failed round trip alone has no restart authority.
- Run the drill weekly and set both freshness windows to 15 days. Rejected: a 35-day inspection window, because it agrees with the old cadence only by accepting evidence that is up to five weeks old. Rejected: `Restart=on-failure` for the drill oneshot, because a manual `systemctl start`, which the restore guide uses as a synchronous gate, would then wait through each restart delay.
- Compare the raw repository `config` file through rclone. Rejected: `restic cat config` on the remote, because it needs the password to match and a second restic lock; restic never rewrites the file, so byte equality is the identity.
- Report a pending reboot in the inspection report only. Rejected for this change: a new metric, because the sender and relay allowlists, the sample budget and the alert rules are one contract in other roles.
- Stagger upgrades with `RandomizedDelaySec=12h` and `FixedRandomDelay=true`, which systemd derives from the machine ID. Rejected: a host-specific `OnCalendar` hour, because systemd computes the next run from the last trigger, so a new hour that has passed today starts an upgrade during the deploy and holds the apt lock. Two hosts can get near slots; the delay still removes the common window.
- Disable tailscaled log upload with a systemd drop-in that sets `TS_NO_LOGS_NO_SUPPORT=true`. Rejected: editing `FLAGS` in the package's `/etc/default/tailscaled`, which the package owns. Rejected: a restart during convergence, because the deployment can be connected through that daemon.

## Contracts and ownership

- `ansible/roles/watchdog`: script, unit, timer, environment template, defaults, note.
- `ansible/roles/backup`: backup script, both service templates, drill timer, defaults, note.
- `ansible/roles/package_updates`, `ansible/roles/tailnet-management`, `ansible/roles/security_audit`, `ansible/roles/runtime-release`: one task or helper change each.
- `ansible/roles/observability_agent/defaults/main.yml`: the restore-drill maximum age only.
- `ansible/group_vars/vpn-p1-web.yml`, `ansible/group_vars/vpn-p2-udp.yml`: the `enable_watchdog` line only.
- `scripts/fleet_inspection.py`: restore windows and the `reboot_required` report field, which every reader of the report validates.
- No secret schema, Terraform or `vpnd` change. The watchdog on the two profiles consumes existing schema keys that the operator must now fill.

## Risks / Trade-offs

- Deployment of the two profiles fails until the probe identities and the canary URL exist → the role asserts refuse before any watchdog file is written; the pull request lists the keys.
- A canary outage together with an API failure restarts Xray → bounded by the per-hour and per-outage budgets.
- A memory limit that is too low kills the probe run → the run then exits non-zero and alerts. 512M is an estimate for an Xray client, a Hysteria client and the configuration test with routing assets; read `MemoryPeak` of the unit after the first runs on each node.
- The identity check refuses a legitimate repository replacement → the operator selects a new `backup.remote.rclone_path` generation, as the rotation guide already requires.
- A weekly drill reads the offsite repository four times as often → the repository holds configuration only.
- The tailscaled setting is inactive until the daemon restarts → all nodes have a pending reboot; `systemctl show -p Environment tailscaled.service` shows the loaded value.

## Migration Plan

Forward: add the probe identities and the canary URL to the encrypted secrets of the two profiles, then run the normal dry run and deployment for each node, and the agent lifecycle for the new restore window and watchdog evidence. Reboot or restart tailscaled in a maintenance window. Rollback: revert the commit and redeploy; the role's disable path removes the watchdog units. An inspection report from an older collector copy is refused, because the controller sends its own copy of the collector with each run.
