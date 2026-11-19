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
- Assumption: implementation language follows the existing role scripts (Python 3.12 standard library) unless a pinned library fits better.

## Contracts and ownership

- `ansible/roles/subscription-host/` (templates, files, tasks), `ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2` and its test template, `contract/observability-metric-manifest.example.json`, `tests/unit/`.
- Serialized lane: alert rule template shared with D3, D5 and D6; land in order D3, D2, D5, D6.

## Risks / Trade-offs

- Cardinality or abuse flood -> label bounds, rate and size limits.
- Report poisoning by a token holder -> cohort token is shared per cohort, so alerts need a minimum attempts floor and D5 compares with sentinel data.
- Correlation of reports with IPs -> no IP stored, categorical log policy.

## Migration Plan

Forward only; the endpoint ships disabled by default and is enabled by the operator through role variables. Rollback disables the vhost location and the aggregator unit.
