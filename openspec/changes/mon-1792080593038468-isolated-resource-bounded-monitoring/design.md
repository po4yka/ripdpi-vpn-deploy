## Context

The current roles already implement co-hosted private Prometheus/Alertmanager/relay, vmagent persistent queue, aggregate slices, disk-reserve latch, and a separately deployable private Kuma observer. This change accepts that positive implementation without external infrastructure and adds a missing representative historical-cardinality case. The owner explicitly changed scope on 2026-10-15; the prior live-acceptance task is retired separately, preserving its original unpassed evidence.

## Goals / Non-Goals

- Goal: ship deployable monitoring with source, hosted CI and isolated real-runtime acceptance under unchanged resource ceilings.
- Goal: verify exact ten-node-cardinality historical replay and failure/rollback boundaries against actual managed runtimes.
- Non-goal: provider access, real host deployment, real Telegram messages/human receipts, live VPN performance, infrastructure purchase or cutover.
- Non-goal: claim seven-day capacity, hard filesystem quota, ten independently enrolled nodes, or outside-in VPN reachability from this workload.

## Decisions

- Keep pinned Prometheus collector, Alertmanager, vmagent sender and Kuma. No new dependency, runtime installer or compatibility branch is added.
- Retain collector 512 MiB/20% CPU and agent 192 MiB/10% CPU slices, zero swap, bounded queue/retention, and persistent reserve latch. Public nginx remains in its original slice/master.
- Extend the canonical enabled collector scenario with 20,000 base series (ten technical fixture labels, 2,000 series each), a current and a 24-hour-old sample for each, and 2,000 churn series: 42,000 samples total. Submit through the real managed sender's fixture import endpoint. Production scrape allowlists and limits remain unchanged. Existing mTLS tests independently verify enrolled identity boundaries.
- Deliver current values first, stop only private ingestion, persist older values, restart the managed sender, recover ingestion, then require all per-node counts, sums and original timestamps for both generations. Check no loss, unchanged collector/public nginx PIDs, no unexpected sender restart or memory events, fixed cgroup ceilings and allocated collector storage below 2 GiB. Record memory peak, CPU statistics and replay duration. This bounded representative workload is not a seven-day capacity simulation.
- Keep real TLS trusted/revoked/wrong-SAN, queue saturation, clean/SIGKILL historical nonce, failed activation rollback and allocated-block pressure scenarios. Portable producer/verifier tests complement canonical runtime execution; they cannot replace it.
- Require actual pinned Kuma push acknowledgement, missing/never-started monitor timing, restart persistence and isolated encrypted restore. Real notification delivery is outside scope; stale/failed relay proof must continue withholding a healthy delivery signal.

## Contracts and ownership

- Monitoring lane owns `ansible/roles/observability_control_plane/molecule/enabled/tasks/bounded-runtime.yml`, that role's `CLAUDE.md`, `tests/unit/test_observability_resource_bounds.py`, and this change's proposal/spec/design/verification artifacts.
- Integration lane owns shared runbook, portfolio lifecycle, execution IDs, task board, CI coordination and archival. Shared files are serialized. Workers preserve other changes and perform no live actions.
- Terraform, cloud-init, real credentials, external accounts and actual VPN hosts are untouched. Existing Ansible roles own runtime state; Make remains the operator surface; secrets/schema/topology and CLI consumers keep their implemented single contract.

## Risks / Trade-offs

- Canonical Debian Molecule image is amd64; the current local Docker host is arm64 without compatible execution. Hosted native amd64 CI must supply canonical runtime results; local source tests do not accept it.
- Historical replay may expose resource pressure at supported cardinality; failure remains fatal. Do not reduce the workload or raise ceilings to pass.
- Isolated observer placement proves processes and persistence, not actual network/power independence. Future deployment still requires separate host admission, private connectivity, backup storage, credential authority, real notifications and matched VPN non-regression before cutover.
- Receiver out-of-order admission is relative to its newest TSDB timestamp. The seven-day setting is not a queue-age, wall-clock durability or measured capacity promise.

## Migration Plan

1. Preserve the original live-task history and record its separate cancellation; do not transfer missing live evidence into success.
2. Add and run the bounded fixture and portable producer/verifier regressions; keep old active-input rejection and rollback behavior intact.
3. Run focused tests, snapshots, lint, task/OpenSpec validation and the full source gate. Publish the exact SHA and require all selected hosted CI, including enabled collector/agent scenarios and real observer runtime evidence.
4. Record exact observed source/isolated-runtime artifacts and close only after their required gates pass. Dry-run against external hosts, live and live-client categories are not applicable from task creation.
5. Future deployment remains a separate authorized operation. Monitoring-only rollback preserves queue/data/credentials and public VPN configuration; Kuma rollback uses its matched database/image backup.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.
