# role: observability_control_plane — bounded write-only metrics receiver

## Design decisions

Prometheus binds only `127.0.0.1:9090`; nginx is the sole public listener and
accepts only mTLS `POST /remote-write/v1/nodes/<node_id>` requests on 9443.
The default TLS virtual host rejects a missing or incorrect SNI before it can
reach the write-only vhost. Prometheus generations are content-addressed and
immutable; rollback repoints `current.yml` directly at the prior generation.
The exact certificate subject maps to one technical node id. TLS validation
uses the client CA, CRL, `clientAuth` purpose and two distinct server SANs.
Prometheus is installed through `runtime-release` with explicit pins.
When explicitly enabled, expected targets are validated from a repository
inventory and rendered as bounded contract metrics; source/deploy identity,
TSDB capacity, and pipeline status use the existing bounded evidence families.
The protocol-liveness adapter consumes only the canonical evaluator's published
redacted evidence. It maps that evidence to bounded one-hot metrics and never
executes probes or recomputes sentinel, variant, profile, or quorum semantics.
It is separately opt-in and owns only its adapter, units, timer, and one
textfile; disable preserves the canonical evaluator evidence.
Alerting is separately opt-in. Prometheus evaluates immutable validated rules;
Alertmanager remains loopback-only and receives its primary Telegram token only
through a systemd credential. Telegram routing contains only bounded technical
aliases and cannot authorize maintenance or infrastructure actions. The
synthetic pipeline watchdog may target only an explicitly enabled loopback
canary receiver; the independent dead-man sender remains a separate owner.
Enabled alerting requires the private gateway on 127.0.0.1:19094. Only its
separate UID receives the dedicated backend client certificate; Alertmanager
requires that CA on HTTPS 127.0.0.1:9093. Prometheus holds only a sender token.
Owner token digests derive maintenance identity; exact `node`/`policy` scope,
reason and configured finite TTL (default four hours) precede any silence write.
The bounded private journal records attempts/results/expiry and retains ownership
across restart. Alertmanager owns native expiration; no source health is changed.

## What's done well

The role checks available (not total) filesystem capacity, fixed request and
retention bounds before writes, removes the distribution nginx site, and
starts nginx explicitly after `policy_rc_d` installation. It disables only
its units and generated configuration while retaining TSDB data.

## Pitfalls

Do not expose loopback Prometheus, add a query/admin path, decode Remote Write
protobuf in nginx, or replace certificate/path identity checks with an IP
allowlist. Do not overwrite an existing content-addressed generation with
different bytes. Retention cleanup is explicitly not part of disable. Do not
add a second target-discovery path, endpoint labels, notification routes, or
liveness quorum logic here; protocol verdict adaptation remains external.
Do not turn a stale, future, malformed, or unknown published verdict into a
healthy, blocked, or rotation conclusion.
Do not put Telegram tokens in Alertmanager YAML, argv, environment, metrics, or
logs. A missing destination is a pre-mutation refusal, and disabling alerting
removes its unit/config/credential surfaces without deleting Prometheus TSDB.

Do not reuse ingestion CA or certificates for the backend, forward raw silence
API routes, trust an owner in a request body, or grant Telegram authority.
Gateway protocol fixtures are not real Alertmanager C13 integration evidence.

A backend write and local completion audit are not an atomic transaction. If
Alertmanager accepts a request but completion audit persistence fails, return
failure and retain the durable attempt; native finite expiry remains authoritative.

Authority publication snapshots its fixed mutable file set and prior service
states before writes. Ordinary failure restores credentials/configuration and
reloads only previously active services; first-install rollback stops new units
before removing their files. A failed restore retains the private snapshot and
blocks publication/disable until manual recovery. Runtime-release binaries and
abrupt host/process death are outside this configuration rollback boundary.

Previous active AM and gateway must form one chain. Partial active topology is
refused before authority publication; standalone active Prometheus before
alerting enablement is supported. This is not a legacy direct-backend route.

Check mode inspects existing namespace entries without creating a snapshot,
permits absent fresh namespace, and uses native file/template change predictions.
It never activates services, performs readiness HTTP calls, or runs rollback cleanup.
