# operations/resource-bounded-observability Specification

## Purpose
Provide private, bounded small-fleet monitoring as deployable source with positive isolated runtime acceptance, preserving truthful boundaries between that evidence and future live deployment.
## Requirements
### Requirement: REQ-IRBO-BOUNDS — Aggregate runtime isolation

The implementation MUST enforce collector MemoryMax 512 MiB/CPUQuota 20%, agent MemoryMax 192 MiB/CPUQuota 10%, no swap, finite cardinality, a pinned single-worker vmagent queue, finite collector retention and a persistent filesystem-reserve latch. VPN units MUST remain outside monitoring slices. Queue/retention settings MUST NOT be described as filesystem quotas or lossless durability guarantees.

#### Scenario: Restart, overload and filesystem pressure

- **WHEN** isolated real runtimes encounter clean or abrupt sender restart, queue saturation or allocated-block pressure
- **THEN** retained exact historical samples recover within the admitted window, saturation reports delivery loss, the reserve latch stops ingestion and refuses automatic restart, and unrelated public nginx retains its process and listeners.

### Requirement: REQ-IRBO-REPLAY — Bounded ten-node history

The canonical enabled runtime test MUST deliver 2,000 base series for each of ten technical fixture nodes with current and 24-hour-old values plus 200 churn series per node, using unchanged resource ceilings. This 42,000-sample workload MUST NOT establish seven-day capacity or ten independently enrolled hosts.

#### Scenario: Exact replay after receiver outage

- **WHEN** the real managed sender persists historical samples during an ingress outage and restarts before ingress recovery
- **THEN** the collector returns every exact node count, value sum and original timestamp for both current and historical samples, without collector OOM/restart, unexpected sender restart or queue loss, with measured memory/storage/drain duration and unchanged public nginx identity.

### Requirement: REQ-IRBO-PRIVATE — Private authenticated ingestion

The implementation MUST restrict remote-write ingestion to private-IP mTLS with verified IP SAN, distinct per-agent client identity and revocation. Query/admin/exporter services MUST remain loopback-only. The collector's independent nginx master MUST preserve existing VPN vhosts and public listeners. Secret-bearing data MUST remain absent from logs, argv and published evidence.

#### Scenario: Trusted and untrusted clients

- **WHEN** isolated real TLS clients use trusted, revoked or incorrectly addressed authority
- **THEN** valid ingestion succeeds while revoked/wrong-SAN clients refuse without bypass, and unrelated public nginx remains available.

### Requirement: REQ-IRBO-OBSERVER — Independent observer runtime

The implementation MUST provide a pinned private Uptime Kuma container with bounded resources, N+2 distinct monitor credentials, direct node/pipeline/delivery producers, restricted verified HTTPS push ingress, private administration, and encrypted quiesced backup with isolated restore. Observer placement MUST be independent of the collector before deployment.

#### Scenario: Missing signals and recovery

- **WHEN** isolated pinned Kuma receives qualified signals and later loses node/pipeline or delivery pushes
- **THEN** actual monitors detect missing and never-started signals within configured bounds, preserve monitor state through restart and recover from encrypted backup in an isolated instance with notifications disabled.

### Requirement: REQ-IRBO-DELIVERY — Honest relay evidence

The implementation MUST distinguish fresh-message send from edit receipts and API acknowledgement from human receipt, require distinct primary/secondary notification authority, and withhold success for stale, invalid or failed canaries. Synthetic rule-to-relay receipts MUST be fresh and single-use. Both routes MUST disclose their common Telegram dependency.

#### Scenario: Stale or failed receipt

- **WHEN** an isolated relay/producer receives a stale receipt, failed canary or missing delivery authority
- **THEN** it refuses a healthy delivery heartbeat without logging credentials; actual Telegram delivery and human receipt remain unverified outside this task.

### Requirement: REQ-IRBO-MIGRATION — One contract and reversible publication

The implementation MUST migrate topology, secrets, Make and CLI consumers together, reject obsolete dedicated topology, preserve queue bytes and prior runtime authority after rejected activation, and provide monitoring-only rollback without deleting retained data or altering VPN configuration.

#### Scenario: Rejected activation and rollback

- **WHEN** a real isolated candidate fails acceptance or monitoring is disabled
- **THEN** the previous accepted runtime and retained queue authority recover, owned new monitoring state stops, and unrelated services/data remain intact.

### Requirement: REQ-IRBO-SCOPE — Source completion and deployment boundary

Completion MUST require source gates, exact-revision hosted CI and isolated real-runtime positive acceptance. It MUST NOT require or claim provider access, live deployment, real Telegram delivery, human receipts, live authenticated VPN performance or cutover. Future deployment MUST still require exact-host capacity/private-path/backup admission, credential authority, matched VPN non-regression and explicit cutover approval, without new paid infrastructure or raised resource limits.

#### Scenario: Source complete with no external infrastructure

- **WHEN** source, hosted and isolated runtime gates pass without external infrastructure
- **THEN** completion records that scope, keeps live categories not applicable from task creation and states that external deployment/notification acceptance has not occurred; planning, mocks alone and refusal-only behavior do not satisfy completion.
