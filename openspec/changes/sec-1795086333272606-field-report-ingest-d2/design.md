## Context

The subscription host already serves bundles over nginx (`ansible/roles/subscription-host/`). Prometheus is fed by vmagent; metrics are described by `contract/observability-metric-manifest*.json`.

## Goals / Non-Goals

- A small, bounded, auditable ingest path.
- Non-goal: per-user storage, raw report archive, or any identifier. Non-goal: client code (RIPDPI R3).

## Decisions

- Aggregate in a local process that exposes metrics for the existing vmagent scrape, and keep no raw report on disk. Rejected: writing reports to a database, because it creates retained user-adjacent data.
- Assumption: the endpoint path is `/v1/field-report` on the subscription host vhost and nginx enforces body size and a coarse `limit_req` before the process.
- Rate limiting is nginx `limit_req` per address only. A process-wide bucket behind it was removed after the second security review: it ran before the token check, so an unauthenticated flood starved token holders, and it was a second rate-limit layer on one HTTP route, which the `security-review` checklist forbids. The process authenticates first.
- The ingest writes its aggregate only in its own systemd `StateDirectory`; the role links it into the shared node_exporter textfile directory with a root-owned symlink. Rejected: the textfile writer group, because it lets the internet-facing process create any `.prom` file there.
- The ingest serves one connection at a time, and each connection has a total deadline of 5 seconds, so a client that sends one byte inside every per-read timeout cannot hold the process. nginx buffers the whole body before it connects to the backend, so real requests end far inside the deadline. Rejected: a threading server, because the in-memory aggregate would then need locking for no gain at this request rate.
- Assumption: top-N ASN is 20 and the list is derived from the previous window by the aggregator; the exact N is a role default.
- Assumption: the token check accepts the current and the previous cohort token so D4 rotation does not drop reports.
- `python3-jsonschema` is pinned per supported release in `subscription_field_report.jsonschema_package_versions`; a release without a pin refuses before installation.
- Assumption: implementation language follows the existing role scripts (Python 3.12 standard library) unless a pinned library fits better.

- Owner decision after review: the client gets no ASN on the device. The `network` label (renamed from `asn`) is the SIM operator `<mcc>-<mnc>` for a `sim` report, `as<asn>` for a `server_hint` report and `unknown` for `none`; the `as` prefix keeps an operator code and an AS number apart in one label. Operators and ASNs rank in separate top-N lists (`operator_top_n`, `asn_top_n`) with the same report floor and series budget, so Wi-Fi ASNs cannot crowd out every operator. Rejected: two labels `asn` and `operator`, because every series would carry an always-empty second label and alerts would need two rule sets. Accepted trade-off: the unbounded label rename breaks existing dashboards and queries; nothing is in production.
- Owner decision after review: the ASN comes from the server. `GET /v1/network-hint` runs in the same ingest process, so it shares the cohort token check (first, before any lookup), the loopback listener, the hardening floor and the no-log handler. It has its own nginx per-address zone, the only rate limit on the route. Rejected: a sibling service, because it duplicates the token, unit and nginx plumbing for one lookup.
- The looked-up address is the TCP peer only. nginx sets `X-Network-Hint-Peer` from `$remote_addr` (nginx replaces a client header of the same name), clears `X-Forwarded-For`, `Forwarded` and `X-Real-IP`, and returns 400 when the request carries any of them or the peer header; the vhost has no `real_ip` directive. The ingest keeps the address in a local variable for one bisect lookup.
- Dataset: IPtoASN `ip2asn-combined.tsv.gz`, Public Domain Dedication and License 1.0, compatible with the repository BSD 3-Clause license and needing no attribution (`ansible/roles/subscription-host/THIRD_PARTY_NOTICES.md`). Rejected: MaxMind GeoLite2 ASN (account and EULA, redistribution limits), IPinfo Lite (CC BY-SA share-alike), DB-IP Lite (CC BY attribution on every use). The download URL always serves the latest build, so the pin is the Last-Modified instant plus SHA-256, and the reviewed file lives in the ignored controller directory `.cache/ip-asn/`; `scripts/refresh-ip-asn-dataset.sh` downloads, validates with the ingest's own loader and prints a new pin. Deploy verifies the controller file against the pin before the host changes, and the ingest verifies the SHA-256 again and refuses a malformed or overlapping range. Accepted trade-off: a fresh checkout without the pinned file cannot enable the hint until the operator restores it or pins a new download. The country is the AS registration country, not a geolocation of the address.
- Memory: the table holds about 460000 IPv4 and 120000 IPv6 routed ranges in arrays; loading peaks near 65 MB, inside the existing 128M unit limit.
- The ingest has no TCP listener. A loopback port is open to every local process, and the transport daemons that relay client traffic each keep their own loopback deny rule (the transport-egress normalizer and its UID-scoped nft hook for Xray, XHTTP and Hysteria, application ACLs for Naive and Snell, the kernel martian rule for AmneziaWG); no single rule covers every transport and every local process, so the egress policy does not prove that client traffic cannot reach `127.0.0.1`. `vpn-field-report.socket` therefore owns `/run/vpn-field-report.sock` as `www-data:www-data 0600` and passes it as fd 3; nginx proxies to `http://unix:/run/vpn-field-report.sock:`, and the service runs with `PrivateNetwork=true` and `RestrictAddressFamilies=AF_UNIX`. The `listen_port` setting is removed.

## Contracts and ownership

- `ansible/roles/subscription-host/` (templates, files, tasks, `THIRD_PARTY_NOTICES.md`), `scripts/refresh-ip-asn-dataset.sh`, `.gitignore` (`.cache/ip-asn/`), the label allowlists in `observability_agent` and the relay, `scripts/fleet_rotation.py` and `scripts/field-analytics-evidence.py` (label rename), `ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2` and its test template, `contract/observability-metric-manifest.example.json`, `tests/unit/`.
- Serialized lane: alert rule template shared with D3, D5 and D6; land in order D3, D2, D5, D6.

## Risks / Trade-offs

- Cardinality or abuse flood -> label bounds, rate and size limits.
- Report poisoning by a token holder -> accepted with bounds: the cohort token is shared, so the data is unauthenticated client input. One report adds at most `max_attempts_per_report` attempts, top-N promotion and both alerts need several distinct reports, the relay admits field reports only from configured subscription hosts, and D5 compares with sentinel data.
- Correlation of reports with IPs -> no IP stored, categorical log policy.
- Hint address handling -> the address is in memory for one lookup; the response, logs, metrics and state hold none of it; a forwarding header is refused, so a client cannot ask about another address through nginx.
- Stale or tampered dataset -> pinned SHA-256 checked on the controller and again at start; refresh is an explicit operator step.

## Migration Plan

Forward only; the endpoint ships disabled by default and is enabled by the operator through role variables. Rollback disables the vhost location and the aggregator unit.
