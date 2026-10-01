## Purpose

Provide affordable operational monitoring on an existing small VPN fleet without trading away service performance, authenticated ingestion, or honest failure reporting.

## ADDED Requirements

### Requirement: REQ-RBO-COST — Existing-capacity admission

The implementation MUST create no dedicated VPS, paid volume, paid monitor, or new public DNS record. Deployment MUST require an approved existing host, measured capacity, and the resource/performance gates in design.md. Failure MUST stop before mutation rather than resize or purchase automatically.

#### Scenario: Insufficient shared capacity

- **WHEN** admission finds less than the configured memory or filesystem reserve, missing private connectivity, or an unsupported storage safeguard
- **THEN** deployment refuses with redacted actionable reasons and leaves VPN services unchanged.

#### Scenario: Positive admission

- **WHEN** an approved host passes admission and the operator authorizes deployment
- **THEN** the collector runs on that host without provisioning a dedicated server.

### Requirement: REQ-RBO-BOUNDS — Bounded shared-host consumption

The implementation MUST enforce aggregate collector and agent cgroup limits, bounded scrape cardinality, a pinned vmagent sender with a size-bounded persistent queue, finite collector retention, and a tested disk-reserve safeguard. A retention-size or queue-size setting alone MUST NOT be described as a hard filesystem quota. VPN services MUST remain outside the observability slice. The sender replacement MUST preserve private mTLS, use one ordered remote-write worker, and reject obsolete Prometheus Agent options rather than retaining a compatibility runtime.

#### Scenario: Sender restart during collector outage

- **WHEN** the collector is unavailable and the sender is restarted cleanly or terminated abruptly after unsent samples have reached its persistent queue
- **THEN** the exact pre-restart samples are delivered after collector recovery within the existing resource limits; queue files or fresh post-restart samples alone do not satisfy recovery.

#### Scenario: Persistent queue reaches its configured capacity

- **WHEN** an outage exhausts the bounded queue
- **THEN** any discarded oldest blocks are observable as delivery loss, allocated disk growth remains within the admitted queue overhead and reserve, and status does not claim lossless delivery.

#### Scenario: Sustained ingestion or memory overload

- **WHEN** realistic fleet load or adversarial cardinality exceeds the accepted budget
- **THEN** ingestion is limited or monitoring fails visibly within its own resource boundary, without killing or restarting VPN services.

#### Scenario: Low filesystem reserve

- **WHEN** the tested disk guard threshold is reached
- **THEN** ingestion stops before the protected reserve is consumed, a watchdog signal fails, and automatic restart cannot bypass the latch.

### Requirement: REQ-RBO-PRIVATE — Authenticated private ingress

The implementation MUST expose metrics ingestion only on the collector's existing private interface with verified mTLS and per-agent identities. Prometheus, Alertmanager, exporters, and relay MUST remain loopback-only except that ingress. It MUST preserve unrelated nginx sites and public VPN listeners. Secrets MUST remain encrypted at rest and absent from commands, logs, metrics, and task evidence.

#### Scenario: Untrusted or incorrectly addressed peer

- **WHEN** a client lacks a trusted certificate, uses a revoked identity, or cannot verify the collector IP SAN
- **THEN** ingestion fails closed without TLS bypass or public-listener fallback.

### Requirement: REQ-RBO-WATCHDOG — Independently hosted loss detection

The implementation MUST use Uptime Kuma on an admitted existing host outside the VPN fleet, with private administration and a restricted private push ingress. Each enrolled node MUST send its own heartbeat directly; the collector MUST NOT proxy or synthesize node health. Collector/pipeline and Telegram-delivery monitors MUST have independent conditions and credentials. Minimal heartbeats and technical aliases MUST disclose no VPN identities, metrics, or logs. Push credentials MUST NOT enter request logs or command arguments. No hosted monitoring account is required.

#### Scenario: Collector or node disappears

- **WHEN** a node or collector stops producing fresh qualifying heartbeats
- **THEN** its Kuma monitor becomes down within the tested detection bound in design.md, independently of the collector, and uses the separately verified notification integration.

#### Scenario: Observer or private path fails

- **WHEN** outbound heartbeat requests fail
- **THEN** producers retain bounded failure status, never log secret URLs, and expose external-coverage loss through the surviving primary route without declaring a confirmed VPN outage or a healthy observer.

#### Scenario: Observer restart or upgrade

- **WHEN** the observer restarts or its version changes
- **THEN** the pinned runtime and persisted monitors recover, and an encrypted consistent backup can restore the prior data with its matching image without duplicate live notifications.

#### Scenario: Observer and collector fail together

- **WHEN** both notification-producing hosts are unavailable
- **THEN** the documented coverage reports no guaranteed alert delivery; neither local process supervision nor a saved healthy status counts as independent detection.

### Requirement: REQ-RBO-DELIVERY — Honest notification proof

The implementation MUST preserve the existing custom-bot primary route and use Kuma's native Telegram integration with a distinct secondary bot credential for loss alarms. It MUST report API acceptance separately from human receipt and fresh-message delivery separately from message-edit credentials checks. It MUST NOT claim Telegram-independent transport or a reminder interval without actual validation. Live observer data and backups containing notification credentials MUST be protected as secret material.

#### Scenario: Primary bot loses authorization

- **WHEN** the real relay's periodic credential canary fails or its receipt becomes stale
- **THEN** the delivery heartbeat fails and Kuma detects the stale signal within its configured bound and attempts secondary notification, without leaking either credential or equating detection time with delivery time.

#### Scenario: Both Telegram routes are unavailable

- **WHEN** Telegram has a platform-wide outage and no separately approved email integration exists
- **THEN** status reports the notification-transport coverage gap rather than promising delivery.

### Requirement: REQ-RBO-EVIDENCE — Health is not client reachability

The implementation MUST preserve distinct node-health, collector-health, alert-delivery, and authenticated external client-path states. Missing client witnesses MUST remain unknown/stale. Existing client-path quorum rules MUST NOT be weakened to accommodate removal of dedicated monitoring sentinels.

#### Scenario: Healthy host with no outside witness

- **WHEN** exporters and local protocol checks pass but no fresh authenticated external client result exists
- **THEN** host health may be healthy while client-path health remains unknown, not healthy.

### Requirement: REQ-RBO-MIGRATION — One new contract and reversible cutover

The implementation MUST migrate all active topology, secrets, Make, and operator callers together, reject obsolete dedicated topology explicitly, and retain no compatibility runtime branch. It MUST verify the replacement route before disabling any functioning old route. Rollback MUST disable only new monitoring state, preserve VPN configuration and retained evidence, and require separate approval before deleting resources or secrets.

#### Scenario: Incomplete replacement or failed performance gate

- **WHEN** notification acceptance or shared-host non-regression fails
- **THEN** cutover stops, new monitoring is disabled safely, and the task stays open with the failed gate identified.

#### Scenario: Positive completion

- **WHEN** source gates, real failure/recovery drills, approved human receipts, and VPN non-regression all pass
- **THEN** completion records those distinct proofs; planning, mocks, API receipts alone, and refusal-only behavior cannot close the feature.
