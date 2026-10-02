# role: observability_control_plane — bounded write-only metrics receiver

## Design decisions

Prometheus binds only `127.0.0.1:9090`; an isolated unprivileged nginx master
accepts only private-IP mTLS `POST /remote-write/v1/nodes/<node_id>` on 9443.
The existing nginx binary runs with its own configuration, pid and temporary
directory; shared VPN nginx units, sites and 80/443 listeners are never touched.
Its IP SAN is verified without DNS or SNI. Prometheus generations are content-addressed and
immutable; rollback repoints `current.yml` directly at the prior generation.
The exact certificate subject maps to one technical node id. TLS validation
uses the client CA, CRL, `clientAuth` purpose and the exact private server IP SAN.
Prometheus is installed through `runtime-release` with explicit pins. Every
receiver process uses the dedicated `observability-prometheus` account, never
the distro node exporter's `prometheus` UID or home. Every
dedicated collector service, including ingress, relay and adapters, belongs to
`observability-collector.slice` (512 MiB, 20% CPU, IOWeight 10, no swap).
Blocks retain at most seven days/1 GiB; WAL/head remain subject to the separate
2 GiB operational high-water guard, not a promised filesystem quota. Admission
precedes account/package writes and requires 1 GiB MemAvailable, allowance plus
max(5 GiB,20% filesystem) reserve, and measured burst/stop headroom. The guard
checks every five seconds; its ten-second systemd watchdog bounds a stalled
scan. Headroom covers twice measured peak writes over watchdog plus enforced
receiver stop timeout. Guard loss stops receiver and ingress via BindsTo;
the durable latch survives disable and requires explicit operator inspection
and recovery. Arithmetic tests are not actual-filesystem burst admission.
The durable latch is owner-private (`0600`); ingress and systemd only test its
existence and do not need read access to its contents.
When explicitly enabled, expected targets are validated from a repository
inventory and rendered as bounded contract metrics; source/deploy identity,
TSDB capacity, and pipeline status use the existing bounded evidence families.
The protocol-liveness adapter consumes only the canonical evaluator's published
redacted evidence. It maps that evidence to bounded one-hot metrics and never
executes probes or recomputes sentinel, variant, profile, or quorum semantics.
It is separately opt-in and owns only its adapter, units, timer, and one
textfile; disable preserves the canonical evaluator evidence.
An enabled collector requires primary alerting. Prometheus evaluates immutable validated rules;
Alertmanager remains loopback-only and sends bounded authenticated webhooks to
a separate loopback relay. Host and adapter metrics arrive only through the
cohosted agent's metric/label allowlist; the collector never scrapes raw node
exporter metrics a second time. Its sole local scrape retains only bounded
Alertmanager notification counters and integration labels.
Confirmed sender discards trigger delivery-loss alerts; byte, block and row
counters are compared to zero separately, never added as interchangeable units.
Only that relay receives the primary Telegram token
through a systemd credential. Its separate random relay credential comes from
the private secrets document and is never derived from the Prometheus sender
authority. Telegram routing contains only bounded technical
aliases and cannot authorize maintenance or infrastructure actions. The relay
owns two bounded delivery attempts, escaping, redaction, truncation and exact
omission counts; fixed group and repeat intervals bound route frequency. A
synthetic rule-to-relay canary carries a fresh evaluation timestamp; replay
cannot refresh its receipt. The real relay sends a silent message daily and
edits its changing sequence every five minutes on an authenticated request.
Durable send/edit receipts report API acceptance, never human receipt. Only
the relay's persistent dedicated account receives the bot token. Kuma
producers consume bounded receipts through loopback endpoints.
Pipeline expected nodes must exactly match the enrolled ingestion identities,
including the collector's own cohosted agent; omissions fail before mutation.
Obsolete deadman runtime input is rejected; an active old alarm route blocks replacement
pending explicit verified cutover, and old secret material is retained.
Enabled alerting requires the private gateway on 127.0.0.1:19094. Only its
separate UID receives the dedicated backend client certificate; Alertmanager
requires that CA on HTTPS 127.0.0.1:9093. Prometheus holds only a sender token.
The gateway opens its five credentials through systemd's exact
`$CREDENTIALS_DIRECTORY` path and does not depend on a credential-directory cwd.
Systemd may expose system credentials as read-only `0440 root:root` files inside
that private mount; gateway metadata checks accept only that exact loaded form or
an owner-private `0400` file and preserve file errors separately from JSON errors.
Owner token digests derive maintenance identity; exact `node`/`policy` scope,
reason and configured finite TTL (default four hours) precede any silence write.
The bounded private journal records attempts/results/expiry and retains ownership
across restart. Alertmanager owns native expiration; no source health is changed.

## What's done well

The role checks available (not total) filesystem capacity, fixed request and
retention bounds before writes. It disables only its units and runtime
configuration while retaining TSDB, latch, relay receipts and credentials.

## Pitfalls

- The disk guard reserves the remaining 2 GiB physical sender-queue allowance on a shared filesystem, including before that queue exists. This reserve stays protected after collector stop so a queued sender cannot consume the host reserve. Separate filesystems are accounted independently; an over-budget or unsafe queue fails closed.

Do not expose loopback Prometheus, add a query/admin path, decode Remote Write
protobuf in nginx, or replace certificate/path identity checks with an IP
allowlist. Do not overwrite an existing content-addressed generation with
different bytes. Retention cleanup is explicitly not part of disable. Do not
add a second target-discovery path, endpoint labels, notification routes, or
liveness quorum logic here; protocol verdict adaptation remains external.
Do not turn a stale, future, malformed, or unknown published verdict into a
healthy, blocked, or rotation conclusion.
Do not put Telegram tokens in Alertmanager YAML, argv, environment, metrics, or
logs. Alertmanager holds only the relay authentication credential. A missing
or reused relay credential is a pre-mutation refusal. The relay never follows an
HTTP redirect away from the exact Telegram API destination. Disabling removes both
alerting units and active configuration without deleting credentials or the
Prometheus TSDB.

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
Every loopback authority-readiness request disables proxy inheritance; local
transaction health must never depend on ambient controller proxy settings.

Previous active AM and gateway must form one chain. Partial active topology is
refused before authority publication; standalone active Prometheus before
alerting enablement is supported. Preserve the previous Alertmanager generation
only while activating a distinct candidate; an unchanged converge must retain
the existing rollback generation. This is not a legacy direct-backend route.

Check mode inspects existing namespace entries without creating a snapshot,
permits absent fresh namespace, and uses native file/template change predictions.
It never activates services, performs readiness HTTP calls, or runs rollback cleanup.
