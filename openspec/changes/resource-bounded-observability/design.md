## Context

The existing implementation assumes dedicated collector/deadman hosts, independent failure domains, large fixed retention, and a public mTLS ingress. Its staging plan cannot simply be applied to an existing VPN host. The replacement goal is useful small-fleet monitoring with zero additional recurring infrastructure purchases; see proposal.md. The previous task remains open and its partial staging evidence is not transferable acceptance.

Read-only provider inventory on the planning date showed one allocated 4 GiB / 2 vCPU node and two 2 GiB / 1 vCPU nodes. This identifies a candidate, not available memory, filesystem capacity, private-network readiness, or deployment permission. No shared-host performance measurement has been made.

The operator selected Uptime Kuma instead of hosted heartbeat monitoring. An existing ARM64 always-on host outside the VPN fleet is the candidate observer; its identity, current resources, storage, private connectivity and independence still require preflight. Choosing this candidate does not authorize changing unrelated services or weakening access controls.

## Goals / Non-Goals

- Goal: metrics, actionable primary alerts, independent missing-node/collector/delivery alarms, and safe shared-host operation for up to ten nodes.
- Goal: zero new VPS/volume/DNS purchases and no public monitoring endpoint.
- Non-goal: collector high availability, long-term metrics storage, new dashboards, new cloud infrastructure, or a new protocol probing framework.
- Non-goal: claiming outside-in VPN availability without actual authenticated external client witnesses, or completing the previous dedicated-staging acceptance by changing its criteria.

## Decisions

### 1. One co-hosted collector, existing alert engine

Retain Prometheus, Alertmanager, the primary Telegram relay, finite silences, grouping, and existing useful host/protocol rules. Do not replace them with custom threshold scripts. Bind ingestion to the existing private-network IP; keep user-facing/query/admin listeners on loopback and use existing operator access. No Grafana or new public web interface is needed.

Agents retain local exporters and bounded remote-write. The sender is a pinned Apache-2.0 vmagent binary, approved after the real Prometheus Agent restart test failed to deliver historical backlog. This replaces only the sender, not the Prometheus collector, Alertmanager or Kuma. Resolve stable per-architecture archives and checksums before execution; maintain this dependency's security updates separately. At a 60-second scrape interval and 2,000 samples per node per scrape, ten nodes are at most approximately 333 samples/second before collector-local series. Limit local series separately and test receiver aggregate capacity. The inventory manifest remains the expected-target authority; observed samples cannot erase missing targets.

### 2. Enforced budgets, then measured admission

These are initial acceptance budgets, not measurements or proof that the current binaries fit:

| Component | Runtime budget |
| --- | --- |
| Collector services together | Dedicated slice, MemoryMax 512 MiB, CPUQuota 20% of one CPU, low IOWeight |
| Agent, adapters, and heartbeat services together per node | Separate slice, MemoryMax 192 MiB, CPUQuota 10% of one CPU |
| Collector blocks | 7 days and 1 GiB retention-size, whichever removes blocks first |
| Collector total data including WAL/head | 2 GiB operational high-water mark; not a claim of hard quota |
| Agent queue | One remote-write worker, persistent disk queue configured at 512 MiB; upstream minimum rounds this to 512 MiB + 128 bytes; bounded memory buffering within the existing agent slice |
| Agent queue filesystem admission | 2 GiB allowance for allocated segments and overhead, plus the protected filesystem reserve; not a larger logical queue or a hard quota |

On the collector host both slices count: up to 704 MiB memory and 30% of one CPU. Admit only with at least 1 GiB MemAvailable at representative load, and free disk exceeding the data allowance plus a protected reserve of max(5 GiB, 20% of the filesystem). Preserve the existing journald limit; do not silently trade VPN diagnostics for monitoring capacity.

The sender queue is size-bounded, not age-bounded: the prior one-hour WAL setting is removed rather than translated into an unsupported flag. Keep the queue in its own private directory, preserve any retired WAL without pretending it can be replayed by the new binary, and reject obsolete sender options. Account for queue segment and in-memory overhead in measured disk admission; do not describe the queue setting as a hard filesystem quota. Preserve dangling queues and bind the queue to its single receiver before activation; a changed receiver or unknown populated queue must fail before mutation rather than silently delete data or accumulate unbounded queues. Queue saturation may drop the oldest unsent blocks and must expose bounded failure metrics, never silent healthy status. Prove actual pre-restart samples reach the collector after both a clean restart and abrupt process termination during an outage, without increasing the 192 MiB / 10% CPU slice. Keep one worker and no fresh-data bypass workers to preserve sample order for Prometheus. Failed restart, resource or queue-pressure checks block deployment.

Install vmagent under its distinct `/opt/observability-vmagent` release root.
The historical `/opt/observability-agent/current/prometheus` target must remain
unchanged and executable for exact-unit rollback. Reusing one release root for
different binary names would either violate its activation receipt or break
the prior public symlink; retaining the old root is rollback preservation,
not a second selectable production sender.

Use supported per-directory filesystem quota when available without repartitioning; otherwise require a separately tested reserve guard with bounded sampling interval and measured worst-case write headroom. The guard latches ingestion off, stops receiver writes, and requires explicit recovery after space inspection. Retention does not bound WAL/head peak size. If burst headroom cannot be demonstrated on the actual filesystem, admission fails. The safeguard covers monitoring writes, not unrelated processes exhausting the disk.

The acceptance load test must include ten-node cardinality, remote-write outage/recovery, churn, restart, and disk pressure. For live admission compare at least three matched baseline/monitoring-enabled VPN runs under representative traffic: no more than 5% median throughput loss, 10% p95 latency increase, and no attributable new connection failures or VPN restarts. Noise that prevents a meaningful comparison leaves the gate unverified, not passed. Never raise budgets or resize automatically to pass.

### 3. Private ingress and composable host capabilities

Replace exclusive observability host classes with an explicit capability set: each enrolled VPN host is VPN-capable and exactly one also carries collector capability. The observer is a separate typed Uptime Kuma endpoint bound to an existing host, not a newly provisioned fleet node. Remove mandatory dedicated deadman/sentinel entries from this contract. Keep authenticated client witnesses in their own existing liveness contract, including its quorum requirements.

Require working private connectivity before deployment; do not implicitly enroll hosts or change tailnet authority. Ingestion on private-IP:9443 uses the current private CA with verified IP SAN, a distinct client certificate per agent, and tested revocation. Extend certificate preparation and its validation for IP SAN, not insecure TLS or invented public names. Shared nginx remains owned by its existing roles. To charge private ingress to the collector's resource budget, observability uses the installed nginx binary in an independent master/unit and configuration inside its slice. It adds/removes only this private ingress and must not remove the distribution/default site, restart global nginx or alter unrelated 80/443 listeners.

### 4. Self-hosted Uptime Kuma outside the VPN fleet

Run one pinned stable Uptime Kuma container on the existing independent host, using its existing container runtime. Resolve and verify the exact release and architecture-specific image digest before implementation acceptance; never use a floating tag or build the image on the observer. Do not mount the Docker socket, use privileged mode, or attach unrelated host directories. Use a private local data directory, not network storage. Start with a 512 MiB container memory ceiling, 25% of one CPU, and bounded logs; require 768 MiB MemAvailable and 3 GiB free local data allowance plus the host reserve before deployment. These are test budgets, not measured compatibility claims. Failure of load or restart tests stops deployment; it does not permit raising limits or purchasing hardware automatically.

Bind the application to loopback. Operator administration uses an authenticated private access path; VPN senders get only a private HTTPS reverse-proxy route to the push endpoint, never the UI, setup, websocket administration, metrics or status pages. Verify the server certificate, restrict source identities to the enrolled nodes, suppress token-bearing request logging on both proxy and application, and require private connectivity before activation. No public port, DNS record, router forwarding or new network enrollment is implicit. Keep the existing host's proxy sites and services untouched.

Allocate N node push monitors + one collector/pipeline monitor + one delivery monitor: five for the initial three-node fleet, twelve at the ten-node limit. Use supported upstream setup and monitor configuration surfaces; do not edit the database directly or assume a third-party provisioning client is approved. Persist the configured private database and document authenticated restore and reconfiguration. Source renderability is not proof that those monitors were actually configured.

Each node sends its own minimal heartbeat every 60 seconds after current local checks. Target a down transition within 180 seconds of the last accepted signal, including the observer scheduler; configure and test the pinned Kuma interval/retry behavior to meet that bound rather than copying another service's period/grace fields. The collector heartbeat has the same schedule and requires fresh expected scrapes, successful rule evaluation, reachable Alertmanager, and a current synthetic rule-to-relay receipt. A stale receipt cannot be refreshed by replaying a cached success. Failed conditions stop success pings; explicit failure may accelerate detection but is not the only failure path. Missing or never-started monitors must be detected during acceptance, not assumed healthy.

The delivery heartbeat runs every five minutes only after the real relay successfully edits one dedicated canary message with a changing non-sensitive sequence. Configure and test a down-transition target of ten minutes from the last accepted signal, including scheduler delay. The relay also sends a new silent canary message daily, requiring a send receipt younger than 26 hours. Editing tests token/chat access; it does not prove the send path. A send-only defect may therefore take up to 26 hours plus the ten-minute detection window to surface. Human receipt is a separate acceptance check, never inferred from API success. Stale/deleted message IDs fail visibly; recreating the message requires a successful actual send.

Deadlines describe monitor transitions, not guaranteed Telegram delivery latency. Configure Kuma's native Telegram integration with a distinct secondary bot credential; do not copy the primary relay token. Issuing a missing secondary credential requires explicit authority. Both routes still share Telegram as a transport. An existing approved SMTP service may provide a separately tested email fallback; no new mail account, paid provider, or relay is implicit. Configure bounded repeat notifications using the pinned version's supported settings and verify actual intervals; do not inherit another service's reminder promises. Keep any existing functional secondary route until explicit cutover approval.

Push URLs are per-monitor bearer credentials held in SOPS and loaded through systemd credentials, never argv or logs. Allowlist the private observer HTTPS destination, verify TLS, disable redirects, use bounded timeouts and retries, and omit optional messages, metrics and diagnostic payloads. Accept success only from Kuma's expected application acknowledgement, not any HTTP 200 page. A stolen push token can forge freshness: private ingress, distinct credentials, protected producer access and rotation reduce but do not eliminate this limitation. No hosted monitoring service receives node IPs or timing, though Telegram still receives notification traffic.

The collector checks observer reachability and heartbeat-send failures through its primary alert route. A private health response proves process reachability, not working alert evaluation or Telegram delivery; acceptance must include a controlled missing-push drill and a human-observed secondary notification. On observer loss, report external coverage unavailable, not a simultaneous confirmed VPN outage. On collector loss, Kuma remains able to alert. Simultaneous loss of collector and observer cannot guarantee notification. Shared private-network failure is also a common-mode dependency and must not be mislabeled as protocol failure.

Back up the entire quiesced Kuma data directory, including SQLite WAL state, to an encrypted owner-controlled backup on separate existing storage. Credentials may exist in the live application database: protect that directory and backups as secrets, and never claim SOPS encryption of configuration also encrypts the live database. Before upgrade, preserve the previous digest and make a consistent encrypted backup; test restore into an isolated instance with notifications disabled before activating it. Container rollback alone is not a database-schema rollback. Do not run old and restored monitors concurrently or delete either dataset automatically.

### 5. Consent and spending boundaries

Additional recurring VPS/service subscription target: zero. Existing equipment still consumes power, storage and maintenance time. No account, monitor, integration, token, DNS record, or server is created during planning. Uptime Kuma is the approved product choice; the existing observer host remains subject to identity/capacity admission. Credential actions, live tests and cutover remain bounded operator actions. If existing capacity, independent connectivity or backup storage is unsuitable, stop with the exact unmet requirement; do not restore the expensive topology or hosted service silently.

## Contracts and ownership

- Terraform/provider roots: no new resources and no schema changes needed for this architecture. Existing cleanup and infrastructure controls remain unchanged.
- Ansible: `observability_control_plane`, `observability_agent`, shared nginx integration, monitoring/watchdog adapters, and replacement heartbeat service own bounded runtime state. Retire obsolete dedicated-deadman deployment paths as part of the single contract migration, not an indefinitely supported second mode.
- Observer: a dedicated `observability_kuma` role and exact-host playbook own only the pinned container, private ingress, data/backup configuration and its lifecycle. The existing host stays outside Terraform fleet provisioning and VPN profiles. Preserve the host's existing repository/service ownership; do not import VPN baseline or firewall roles onto it. Runtime installation or access-authority changes require separate approval if preflight finds them absent.
- Scripts/contract: inventory validation, rendering, readiness, acceptance, credential preparation, and operator output migrate together. Preserve revocation, redaction, finite request limits, and desired-target semantics.
- Secrets: update `secrets/schema.json`, validator/coverage, examples, and consumers together for per-check ping credentials and IP-SAN TLS. No plaintext in plan/state/output. Do not delete old secret material without explicit approval.
- Make remains the canonical render/validate/deploy/verify surface. Audit vpnd callers and help; update any affected callers without adding a separate orchestrator. No new production dependency is approved implicitly.
- Tests/runbooks: update fixtures, snapshots, role guidance, co-hosting rollback, bounds, delivery deadlines, trust limitations, and distinct evidence states together.

## Risks / Trade-offs

- Collector loss also loses recent central metrics; independently emitted node checks and external collector check still detect missing signals. Metrics HA is deliberately not purchased.
- Shared host contention can affect VPN before a memory ceiling is reached; CPU/IO controls and measured admission are required. Failed tests mean this design is not deployable on that host.
- Observer hardware, power, local network and Telegram outages remain separate risks. Reachability and local send failures are observable through a surviving primary route; simultaneous total failures cannot guarantee notification. Kuma on the collector itself would violate the independent-placement requirement.
- Private connectivity and filesystem support are unverified. Read-only host preflight requires explicit infrastructure access authorization.
- Existing full client-path and old independent-sink guarantees are not inherited. Removing paid monitoring nodes saves cost by accepting documented coverage limits, not by relabeling local checks.

## Migration Plan

1. Record the approved Uptime Kuma direction and candidate existing observer. Keep the previous task open; any later drop/supersession uses taskctl, never a false done transition.
2. Implement the new contract and all callers in isolated source changes; reject the old shape with actionable errors. Complete credential-free tests and full repository gates.
3. With explicit access permission, run read-only admission on both the collector and independent observer, confirm existing runtime/private connectivity/backup storage, and capture matched VPN baselines. Record a technical alias, not identifying host details, in evidence.
4. With exact-host deployment and credential permission, install the pinned Kuma runtime, configure five push monitors, verify separate notification receipts, and prepare private TLS. Test encrypted backup/restore and observer-outage reporting through the primary route. Do not disable any working old alarm route.
5. With live permission, deploy bounded monitoring to the admitted existing host, then agents. Verify private listeners and unchanged VPN configuration before drilling failures. Use operator-approved reversible service/check interruptions; no unapproved node shutdown.
6. Complete local, hosted CI, live delivery/recovery, storage/memory, and external-client evidence separately. Ask for cutover only after positive acceptance. No new recurring spend or dedicated staging node is required.
7. Rollback stops/disables only new monitoring units/container and removes only their vhost/config integration; retain data and secrets, restore the saved prior monitoring configuration, and verify VPN and surviving alert routes. For a Kuma schema migration use its verified pre-upgrade database backup with the matching image. Never provision old paid nodes as automatic rollback.
