## Context

The existing implementation assumes dedicated collector/deadman hosts, independent failure domains, large fixed retention, and a public mTLS ingress. Its staging plan cannot simply be applied to an existing VPN host. The replacement goal is useful small-fleet monitoring with zero additional recurring infrastructure purchases; see proposal.md. The previous task remains open and its partial staging evidence is not transferable acceptance.

Read-only provider inventory on the planning date showed one allocated 4 GiB / 2 vCPU node and two 2 GiB / 1 vCPU nodes. This identifies a candidate, not available memory, filesystem capacity, private-network readiness, or deployment permission. No shared-host performance measurement has been made.

## Goals / Non-Goals

- Goal: metrics, actionable primary alerts, independent missing-node/collector/delivery alarms, and safe shared-host operation for up to ten nodes.
- Goal: zero new VPS/volume/DNS purchases and no public monitoring endpoint.
- Non-goal: collector high availability, long-term metrics storage, new dashboards, new cloud infrastructure, or a new protocol probing framework.
- Non-goal: claiming outside-in VPN availability without actual authenticated external client witnesses, or completing the previous dedicated-staging acceptance by changing its criteria.

## Decisions

### 1. One co-hosted collector, existing alert engine

Retain Prometheus, Alertmanager, the primary Telegram relay, finite silences, grouping, and existing useful host/protocol rules. Do not replace them with custom threshold scripts. Bind ingestion to the existing private-network IP; keep user-facing/query/admin listeners on loopback and use existing operator access. No Grafana or new public web interface is needed.

Agents retain local exporters and bounded remote-write. At a 60-second scrape interval and 2,000 samples per node per scrape, ten nodes are at most approximately 333 samples/second before collector-local series. Limit local series separately and test receiver aggregate capacity. The inventory manifest remains the expected-target authority; observed samples cannot erase missing targets.

### 2. Enforced budgets, then measured admission

These are initial acceptance budgets, not measurements or proof that the current binaries fit:

| Component | Runtime budget |
| --- | --- |
| Collector services together | Dedicated slice, MemoryMax 512 MiB, CPUQuota 20% of one CPU, low IOWeight |
| Agent, adapters, and heartbeat services together per node | Separate slice, MemoryMax 192 MiB, CPUQuota 10% of one CPU |
| Collector blocks | 7 days and 1 GiB retention-size, whichever removes blocks first |
| Collector total data including WAL/head | 2 GiB operational high-water mark; not a claim of hard quota |
| Agent queue | One remote-write shard, bounded queue, at most one-hour WAL retention |

On the collector host both slices count: up to 704 MiB memory and 30% of one CPU. Admit only with at least 1 GiB MemAvailable at representative load, and free disk exceeding the data allowance plus a protected reserve of max(5 GiB, 20% of the filesystem). Preserve the existing journald limit; do not silently trade VPN diagnostics for monitoring capacity.

Use supported per-directory filesystem quota when available without repartitioning; otherwise require a separately tested reserve guard with bounded sampling interval and measured worst-case write headroom. The guard latches ingestion off, stops receiver writes, and requires explicit recovery after space inspection. Retention does not bound WAL/head peak size. If burst headroom cannot be demonstrated on the actual filesystem, admission fails. The safeguard covers monitoring writes, not unrelated processes exhausting the disk.

The acceptance load test must include ten-node cardinality, remote-write outage/recovery, churn, restart, and disk pressure. For live admission compare at least three matched baseline/monitoring-enabled VPN runs under representative traffic: no more than 5% median throughput loss, 10% p95 latency increase, and no attributable new connection failures or VPN restarts. Noise that prevents a meaningful comparison leaves the gate unverified, not passed. Never raise budgets or resize automatically to pass.

### 3. Private ingress and composable host capabilities

Replace exclusive observability host classes with an explicit capability set: each enrolled host is VPN-capable and exactly one also carries collector capability. The managed watchdog is a typed service configuration, not a fake inventory host. Remove mandatory deadman/sentinel entries from this contract. Keep authenticated client witnesses in their own existing liveness contract, including its quorum requirements.

Require working private connectivity before deployment; do not implicitly enroll hosts or change tailnet authority. Ingestion on private-IP:9443 uses the current private CA with verified IP SAN, a distinct client certificate per agent, and tested revocation. Extend certificate preparation and its validation for IP SAN, not insecure TLS or invented public names. Shared nginx remains owned by its existing roles; observability adds/removes only its own private vhost and must not remove the distribution/default site or alter unrelated 80/443 listeners.

### 4. Native managed heartbeats instead of a dedicated deadman VPS

Choose Healthchecks, not a custom hosted Worker/database scheduler. Its free plan currently offers 20 checks; deployment must verify remaining account quota and integration availability. Allocate N node checks + one collector/pipeline check + one delivery check: five checks for the observed three-node fleet, twelve at the ten-node limit. Account for temporary drill checks inside the same quota; no account sharding or paid upgrade fallback.

Each node sends its own empty-body heartbeat every 60 seconds after current local checks; period 60 seconds plus grace 120 seconds gives a three-minute missing-signal deadline from the last qualifying signal. The collector heartbeat has the same schedule and requires fresh expected scrapes, successful rule evaluation, reachable Alertmanager, and a current synthetic rule-to-relay receipt. A stale receipt cannot be refreshed by replaying a cached success. Failed conditions stop success pings; explicit failure may accelerate detection but is not the only failure path.

The delivery heartbeat runs every five minutes only after the real relay successfully edits one dedicated canary message with a changing non-sensitive sequence. Period five minutes plus grace five minutes gives a ten-minute missing-signal deadline. The relay also sends a new silent canary message daily, requiring a send receipt younger than 26 hours. Editing tests token/chat access; it does not prove the send path. A send-only defect may therefore take up to 26 hours plus check grace to surface. Human receipt is a separate acceptance check, never inferred from API success. Stale/deleted message IDs fail visibly; recreating the message requires a successful actual send.

Deadlines describe managed-check state transitions, not guaranteed Telegram delivery latency. Native integration uses the managed service's separate Telegram bot; it never receives the custom bot token. Both routes still share Telegram as a transport. Recommend native email as a transport-independent fallback only after consent and a real receipt; it is not enabled by this plan. Do not promise hourly Telegram reminders: the documented recurring reminder option is email. Keep any existing functional secondary route until explicit cutover approval.

Managed ping URLs are bearer credentials in SOPS and systemd credential files, never argv or logs. Allowlist the service HTTPS destination, verify TLS, disable redirects, use bounded timeouts and retry limits, and do not attach metrics or diagnostic bodies. Technical aliases still expose source IP and timing to the service. Compared with the prior signed sequence-based deadman, a stolen ping URL can forge freshness; distinct per-check credentials, rotation, and protected producer access reduce but do not eliminate this trade-off. Rejecting that trust model requires revising this design before activation.

### 5. Consent and spending boundaries

Additional recurring infrastructure target: zero. Existing VPN bills remain unchanged; resource use is not free capacity. No account, monitor, integration, token, DNS record, or server is created during planning. External-service consent is pending. Source implementation can proceed once the design is approved; service enrollment, credential actions, approved host selection, live tests, and cutover each remain bounded operator actions. If the free service or existing capacity is unsuitable, stop and revise the design; do not restore the expensive topology silently.

## Contracts and ownership

- Terraform/provider roots: no new resources and no schema changes needed for this architecture. Existing cleanup and infrastructure controls remain unchanged.
- Ansible: `observability_control_plane`, `observability_agent`, shared nginx integration, monitoring/watchdog adapters, and replacement heartbeat service own bounded runtime state. Retire obsolete dedicated-deadman deployment paths as part of the single contract migration, not an indefinitely supported second mode.
- Scripts/contract: inventory validation, rendering, readiness, acceptance, credential preparation, and operator output migrate together. Preserve revocation, redaction, finite request limits, and desired-target semantics.
- Secrets: update `secrets/schema.json`, validator/coverage, examples, and consumers together for per-check ping credentials and IP-SAN TLS. No plaintext in plan/state/output. Do not delete old secret material without explicit approval.
- Make remains the canonical render/validate/deploy/verify surface. Audit vpnd callers and help; update any affected callers without adding a separate orchestrator. No new production dependency is approved implicitly.
- Tests/runbooks: update fixtures, snapshots, role guidance, co-hosting rollback, bounds, delivery deadlines, trust limitations, and distinct evidence states together.

## Risks / Trade-offs

- Collector loss also loses recent central metrics; independently emitted node checks and external collector check still detect missing signals. Metrics HA is deliberately not purchased.
- Shared host contention can affect VPN before a memory ceiling is reached; CPU/IO controls and measured admission are required. Failed tests mean this design is not deployable on that host.
- Managed-service outage and Telegram outage remain separate risks. Local send failures are observable through a surviving primary route; simultaneous total failures cannot guarantee notification.
- Private connectivity and filesystem support are unverified. Read-only host preflight requires explicit infrastructure access authorization.
- Existing full client-path and old independent-sink guarantees are not inherited. Removing paid monitoring nodes saves cost by accepting documented coverage limits, not by relabeling local checks.

## Migration Plan

1. Review this replacement design and resolve managed-service trust/notification consent. Keep the previous task open; any later drop/supersession uses taskctl, never a false done transition.
2. Implement the new contract and all callers in isolated source changes; reject the old shape with actionable errors. Complete credential-free tests and full repository gates.
3. With explicit access permission, run read-only host admission and capture matched VPN baselines. Record a technical alias, not identifying host details, in evidence.
4. With explicit credential/service permission, configure five managed checks for the initial fleet, verify native notification receipts, and prepare private TLS. Do not disable any working old alarm route.
5. With live permission, deploy bounded monitoring to the admitted existing host, then agents. Verify private listeners and unchanged VPN configuration before drilling failures. Use operator-approved reversible service/check interruptions; no unapproved node shutdown.
6. Complete local, hosted CI, live delivery/recovery, storage/memory, and external-client evidence separately. Ask for cutover only after positive acceptance. No new recurring spend or dedicated staging node is required.
7. Rollback stops/disables only new monitoring units and removes only their vhost/config integration; retain data and secrets, restore the saved prior monitoring configuration, and verify VPN and surviving alert routes. Never provision old paid nodes as automatic rollback.
