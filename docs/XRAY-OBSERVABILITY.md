# Xray observability

Xray diagnostics stay local to each node. `StatsService` listens only on
`127.0.0.1:10086`; node_exporter listens only on `127.0.0.1:9100`. Neither
endpoint belongs in the Terraform public-listener contract or the firewall
allowlist.

## What is collected

`xray-stats-exporter.timer` queries StatsService every 60 seconds and writes
`/var/lib/node_exporter/textfile/vpn_xray.prom` atomically. The exporter emits:

- collector success, record count, and collection timestamp;
- cumulative traffic by technical inbound/outbound tag and direction;
- cumulative inbound and outbound traffic under repository-owned technical
  tags.

Per-user counters are disabled in Xray, so client email/name fields never enter
the local StatsService response. UUIDs, short IDs, source addresses,
destinations, and domains are not collected. Raw access/error logs retain the
existing short local rotation policy and are not forwarded.

## Operator check

Run the redacted diagnostic playbook through the normal inventory and optional
Tailscale host override:

```bash
make xray-diagnostics \
  ANSIBLE_LIMIT=<p0-host> \
  ANSIBLE_EXTRA_VARS_FILE=secrets/local/config/<host>-tailscale-vars.yml
```

The command fails if the gRPC query fails, the collector reports failure, or
the textfile evidence is older than 180 seconds. It prints only `vpn_xray_*`
metrics. The override file is limited to management-path variables and is
rejected if it attempts to replace `vpn_service_address` or protocol state.

For a direct on-node check:

```bash
sudo /usr/local/bin/xray api statsquery --server=127.0.0.1:10086
curl --fail --silent http://127.0.0.1:9100/metrics | grep '^vpn_xray_'
systemctl status xray-stats-exporter.timer xray-stats-exporter.service
```

The watchdog also queries StatsService. Three consecutive failures follow the
normal bounded restart/alert policy for `xray.service`; a failed collector
additionally leaves `vpn_xray_stats_collection_success 0` and a failed
oneshot unit visible through node_exporter's systemd collector.

## Interpreting the signal

- `vpn_xray_stats_collection_success 0`: local API, parser, or file-write
  failure; inspect the exporter unit journal.
- Fresh collector timestamps with flat inbound counters: Xray is observable
  but has seen no traffic on that inbound during the inspected interval.
- Increasing authenticated VLESS liveness plus increasing inbound counters:
  both the outside-in user path and server-side accounting are working.

Counters reset when Xray restarts. Use rates/increases in a scraper; do not
treat cumulative values as durable accounting.

Disabling both Xray transports, or converting a host to subscription-only,
stops and removes the exporter timer and deletes its textfile. This prevents a
later node_exporter scrape from presenting stale Xray counters as current.
