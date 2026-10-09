# role: monitoring — local-first observability

## Design decisions

**No external telemetry** — Prometheus node_exporter listens on 127.0.0.1
only. `scripts/probing-summary.sh` pulls metrics via SSH on demand. Nothing
egresses unless the operator runs it.

**Journald retention policy** — a drop-in sets `SystemMaxUse=500M` and
`MaxRetentionSec=14day`. Keeps logs useful without accumulating a corpus
that could be seized. No syslog forwarding.

**Textfile producers use a shared writer group** — monitoring owns the
root-owned setgid and sticky directory, while unprivileged producers such as
honeypot join `node_exporter_textfile`. This keeps collector reads available
without granting those producers ownership or cross-producer replacement.

**Xray diagnostics exclude user identity at the source** — per-user counters
stay disabled. A hardened one-shot queries loopback StatsService every 60
seconds and exports only repository-owned technical inbound/outbound tags. It
runs as node_exporter's own account (`prometheus` by default,
`monitoring.node_exporter_user`) so its atomic textfile can remain 0600
instead of granting group or world read access.

**Xray rotation uses active-service restart** — the pinned runtime has no
supported HUP log-reopen contract. Rotation restarts only an active Xray and
requires active state afterward; restart failure propagates from logrotate.
This briefly interrupts existing connections while restoring writable logs.

## What's done well

- **Logrotate with retention** — monitoring owns one package-wide Nginx policy
  and the Xray policy, both with daily rotation and 14-day retention. The role
  removes the old overlapping `nginx-vpn` drop-in so every log has one owner.
- **Prometheus textfile collector enabled** — `--collector.systemd` and
  `--collector.processes` ship systemd unit states and process stats without
  any extra configuration.
- **Failure is itself observable** — collector errors atomically replace stale
  counters with `vpn_xray_stats_collection_success 0`; the failed oneshot is
  also visible through the systemd collector.
- **Disable is convergent** — removing the last Xray transport stops and removes
  the exporter timer, unit, binary, and textfile instead of exposing stale
  counters from an earlier profile.

## Pitfalls

- **Fresh-host check mode has no node_exporter unit yet** — the package task
  reports its planned change without installing the service. Check service
  state only when the package was already present; normal convergence must
  still enable and restart node_exporter.
- **node_exporter on a public port = fingerprint** — never bind anything
  other than 127.0.0.1. The role's Molecule verify asserts the loopback bind;
  `verify.yml` only scrapes the loopback address and does not prove the
  port is closed publicly.
- **Logrotate postrotate signal** — the Nginx logrotate stanza uses
  `systemctl reload nginx`. If nginx is not running (e.g. on a Hysteria-only
  node), the `|| true` guard prevents a failure, but confirm the service name
  matches your deployment.
- **Nginx logrotate globs must not overlap** — never add a second policy for a
  subset of `/var/log/nginx/*.log`; logrotate rejects the complete configuration
  when the same log appears twice.
- **No alerting included** — by design. Alerting is operator-side, via
  `install-operator-crons` on a workstation, not on the server.
- **Counters reset with Xray** — graph rates or increases. They are diagnostic
  evidence, not a durable usage or billing ledger.
