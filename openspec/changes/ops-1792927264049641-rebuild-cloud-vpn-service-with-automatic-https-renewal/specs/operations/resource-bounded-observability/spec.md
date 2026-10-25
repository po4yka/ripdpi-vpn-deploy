## Purpose

Keep bounded monitoring independent of personal devices and distinguish source evidence from the authorized cloud rollout.

## MODIFIED Requirements

### Requirement: REQ-IRBO-SCOPE — Source completion and deployment boundary

Source completion MUST require source gates, exact-revision hosted CI and isolated real-runtime positive acceptance. It MUST NOT by itself require or claim provider access, live deployment, external notification delivery, human receipts, live authenticated VPN performance or cutover. Completion MUST distinguish that source evidence from an authorized live deployment and client evidence. A future deployment MUST require exact-host capacity, private-path and backup admission, credential authority, matched VPN non-regression and explicit cutover approval. An independent cloud observer MAY be provisioned within a separately approved provider and cost bound; this MUST NOT restore the retired dedicated collector topology or raise existing monitoring resource limits. Production admission MUST be explicit. Notifications and human receipt MUST NOT be claimed without actual authority and observed delivery.

#### Scenario: Authorized cloud-only rollout

- **WHEN** an owner approves the exact cloud topology and costs and personal devices are excluded
- **THEN** an independent cloud observer can be admitted after its own checks, collector and agent limits remain unchanged, and local, live, client and notification results are reported separately.

#### Scenario: Source complete with no external infrastructure

- **WHEN** source, hosted and isolated runtime gates pass without external infrastructure
- **THEN** completion records that scope, keeps live categories not applicable from task creation and states that external deployment/notification acceptance has not occurred; planning, mocks alone and refusal-only behavior do not satisfy completion.

### Requirement: REQ-IRBO-OBSERVER — Independent observer runtime

The implementation MUST provide a pinned private Uptime Kuma container with bounded resources, distinct monitor credentials, direct node and pipeline producers, restricted verified HTTPS push ingress, private administration, and encrypted quiesced backup with isolated restore. Observer placement MUST be independent of the collector before deployment. Notification-enabled mode MUST include the additional delivery producer and N+2 monitors. Explicit panel-only mode MUST use N+1 node/pipeline monitors, MUST NOT require external bot credentials, and MUST NOT fabricate a delivery heartbeat or message receipt.

#### Scenario: Missing signals and recovery

- **WHEN** isolated pinned Kuma receives qualified signals and later loses node/pipeline or delivery pushes
- **THEN** actual monitors detect missing and never-started signals within configured bounds, preserve monitor state through restart and recover from encrypted backup in an isolated instance with notifications disabled.

#### Scenario: Panel-only observer

- **WHEN** the owner selects panel-only monitoring without external notification credentials
- **THEN** node and pipeline monitors operate with distinct credentials and bounded resources, the panel exposes their state privately, and delivery remains explicitly disabled.

### Requirement: REQ-IRBO-DELIVERY — Honest relay evidence

Notification-enabled mode MUST distinguish fresh-message send from edit receipts and API acknowledgement from human receipt, require distinct primary/secondary notification authority, and withhold success for stale, invalid or failed canaries. Synthetic rule-to-relay receipts MUST be fresh and single-use. Both Telegram routes MUST disclose their common dependency. Panel-only mode MUST explicitly disable the relay and delivery heartbeat, without treating absent notification authority as successful external delivery.

#### Scenario: Stale or failed receipt

- **WHEN** an isolated relay/producer receives a stale receipt, failed canary or missing delivery authority
- **THEN** it refuses a healthy delivery heartbeat without logging credentials; actual Telegram delivery and human receipt remain unverified outside this task.
