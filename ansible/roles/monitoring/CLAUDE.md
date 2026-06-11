# role: monitoring — local-first observability

## Design decisions

**No external telemetry** — Prometheus node_exporter listens on 127.0.0.1
only. `scripts/probing-summary.sh` pulls metrics via SSH on demand. Nothing
egresses unless the operator runs it.

**Journald retention policy** — a drop-in sets `SystemMaxUse=500M` and
`MaxRetentionSec=14day`. Keeps logs useful without accumulating a corpus
that could be seized. No syslog forwarding.

## What's done well

- **Logrotate with retention** — xray and nginx-vpn logs rotated daily with
  14-day retention. No long-term log corpus to subpoena.
- **Prometheus textfile collector enabled** — `--collector.systemd` and
  `--collector.processes` ship systemd unit states and process stats without
  any extra configuration.

## Pitfalls

- **node_exporter on a public port = fingerprint** — never bind anything
  other than 127.0.0.1. Verified by `verify.yml`.
- **Logrotate postrotate signal** — the nginx-vpn logrotate stanza uses
  `systemctl reload nginx`. If nginx is not running (e.g. on a Hysteria-only
  node), the `|| true` guard prevents a failure, but confirm the service name
  matches your deployment.
- **No alerting included** — by design. Alerting is operator-side, via
  `install-operator-crons` on a workstation, not on the server.
