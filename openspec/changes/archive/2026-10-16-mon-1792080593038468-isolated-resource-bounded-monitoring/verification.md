---
task_id: "MON-1792080593038468"
change: "mon-1792080593038468-isolated-resource-bounded-monitoring"
commit_sha: "3010dfb517b84cd7fbe9c3512b30b87d63b64fe8"
local: "passed"
local_evidence: "Recorded focused Mac evidence: 139 monitoring cases, final 32 resource cases, 56 workflow/resource cases, 163 snapshots, production-profile lint and full-history secret scanning passed. The monolithic local gate failed on registry timeout and its queued retry was cancelled; no complete new local success is claimed. Owner-approved full source coverage passed in actual M1 hosted CI; the failed monolithic local run is not reclassified as passing."
remote_ci: "passed"
remote_ci_evidence: "Actual integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8: CI 38792726270 completed all 88 jobs successfully with zero failed, cancelled, skipped or pending jobs. CodeQL 38792726004 completed both jobs successfully with zero open repository alerts. Native integration 116621390880, collector 116621391330, agent 116621391025, Kuma 116621392357 and transport runtime acceptance 116621390735 all passed."
dry_run: "not_applicable"
dry_run_evidence: "Source-only task created after owner decision 2026-10-15; no external-host check mode is in scope."
staging: "not_applicable"
staging_evidence: "No external staging deployment is in scope. Positive isolated runtime acceptance remains required under remote_ci and artifact; it is not host staging evidence."
live: "not_applicable"
live_evidence: "Source-only task; external deployment, real Telegram/human receipt and cutover are excluded, not passed."
client: "not_applicable"
client_evidence: "Live authenticated VPN performance is excluded; isolated runtime traffic does not claim external client acceptance."
artifact: "passed"
artifact_evidence: "Actual M1 main CI 38792726270 passed all source schemas, contracts, snapshots and isolated runtime acceptance artifacts. Positive canonical collector/agent/Kuma and native client/runtime results are recorded below; no external rollout or notification receipt is inferred."
---

# Verification

## Current integrated main acceptance (passed)

Primary source is `3010dfb517b84cd7fbe9c3512b30b87d63b64fe8`. Main CI `38792726270` completed all 88 jobs successfully with zero failed, cancelled, skipped or pending jobs. CodeQL `38792726004` completed both jobs successfully with zero open repository alerts. All current mapped requirements and applicable source/client/artifact gates passed; external categories retain their original not-applicable scope. Prior numeric measurements are not reused as M1 observations.

## Historical evidence boundary

All requirement rows, commands, outcomes and numeric runtime observations in the following retained sections describe f6ad803e97237d8d8ec3839284d84db974ea986c and its recorded premerge/baseline runs. Their original source/run IDs remain unchanged. They are historical evidence, not current M1 acceptance. Statements that acceptance passed or remained pending apply to their original snapshot. Current integrated acceptance is recorded above and in Observed integrated M1 results below.

This task starts with source and isolated real-runtime scope, per the owner decision on 2026-10-15. The old task's missing live evidence is not transferred or accepted. Future deployment still requires exact-host resource/private-path/backup admission, credentials, real notifications, human receipt, matched VPN performance and approved cutover.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-IRBO-BOUNDS | MON-1792080763077431 | Canonical enabled collector/agent runtime: restart, saturation, allocated-block latch and isolation | passed |
| REQ-IRBO-REPLAY | MON-1792080763077431 | New actual managed-sender 42,000-sample, ten-label-node, 24-hour historical replay | passed |
| REQ-IRBO-PRIVATE | MON-1792080763077431 | Enabled real mTLS ingestion/revoked/wrong-SAN and unchanged public nginx | passed |
| REQ-IRBO-OBSERVER | MON-1792080764176275 | Actual pinned Kuma acknowledgement, missing/never-started timing, restart persistence, encrypted isolated restore | passed |
| REQ-IRBO-DELIVERY | MON-1792080764176275 | Relay/canary/push regressions and actual isolated rule-to-relay receipt | passed |
| REQ-IRBO-MIGRATION | MON-1792080765681879 | Contract/schema/operator obsolete-input tests, snapshots, failed activation/monitoring-only rollback | passed |
| REQ-IRBO-SCOPE | MON-1792080765681879 | Coherent task/verification/runbook scope; exact-SHA full local and selected hosted CI | passed |

## Observed local checks

- `mise exec -- python3 -m pytest -q tests/unit/test_observability_agent_render.py tests/unit/test_observability_control_plane_render.py tests/unit/test_observability_control_plane_generation.py tests/unit/test_observability_resource_bounds.py`: 139 passed before the additional per-sample-value equality regression.
- Final `mise exec -- python3 -m pytest -q tests/unit/test_observability_resource_bounds.py`: 32 passed, including exact workload rows and rejection of corrupted count, sum, per-sample values and timestamps. These execute fixture helpers, not native services.
- `mise exec -- ansible-lint ansible/roles/observability_control_plane/molecule/enabled/tasks/bounded-runtime.yml`: production profile passed with zero failures/warnings before the final equality assertion; final integrated lint remains required.
- `git diff --check`: passed before final integration.
- Current local Docker is arm64. The exact canonical Debian Molecule image is amd64 and `docker run --rm --network none --entrypoint /bin/sh <pinned-image> -c 'uname -m'` returned `exec format error`. This is a local architecture blocker, not a skipped/passed role gate. Hosted amd64 runtime evidence is required.

## Initial remaining gates (superseded by accepted source results below)

- Full source gate, snapshots, task contract and strict OpenSpec validation at the final revision.
- Exact-SHA selected hosted workflows, including canonical `molecule failure (observability_control_plane)` and `molecule failure (observability_agent)` with no selected skips.
- Actual pinned observer timing/persistence/restore runtime evidence; portable mocks and historical claims alone do not accept the new task.
- Final artifacts identify exact source/run revisions and distinguish bounded representative replay from seven-day capacity and real deployment.

Archive remains forbidden while any required category lacks observed complete evidence.

## Exact source collector and sender acceptance (2026-10-15)

CI 38768887914 on `f6ad803e97237d8d8ec3839284d84db974ea986c` passed
canonical enabled collector job 116539283944 and agent job 116539284201.
The collector converged 381 tasks and its idempotence pass observed 347 tasks
with zero changes. Verification finished 33 tasks with zero failures or skips.

- The actual managed sender replayed 42,000 current/historical/churn samples,
  ten fixture node labels and 2,000 base series each, including 24-hour history.
  Exact count, sum, per-sample value and original timestamp assertions passed.
  Replay took 17.220 seconds; allocated collector storage was 1,757,184 bytes
  and collector memory peak was 173,510,656 bytes under the unchanged 512 MiB
  and 20% CPU ceilings. Throttling was observed, not disabled.
- The sender persisted exact historical samples through both clean and abrupt
  restarts (53,248 and 98,304 allocated queue bytes). No drop, unexpected
  restart, memory event or public nginx identity change occurred in replay.
- Actual filesystem pressure latched ingestion off in 5.01 seconds, manual
  restart refused and public TLS remained available. Native saturation wrote
  1,080,225,900 queue bytes with a 1,007,104,000-byte physical peak; intentional
  eviction reported 1,054 blocks / 577,339,629 bytes as loss rather than success.
- This is bounded isolated process/filesystem proof. It does not establish
  seven-day capacity, ten independently enrolled hosts or a real deployment.

## Exact source observer and rollback acceptance (2026-10-15)

CI 38768887914 job 116539285094 passed the actual pinned rootless Kuma
image with 512 MiB / 0.25 CPU and no network. Valid push acknowledgement,
unknown-token rejection, authenticated monitor persistence across restart,
quiesced age encryption and authenticated isolated restore all passed.
Node missing-signal detection was 120.906–122.003 seconds; pipeline was
121.001 seconds, never-started 120.008 seconds and delivery 541.003 seconds.
The restored instance had no network or published ports, blocking notifications.
These are actual application timers and persistence results, not human receipts.

Canonical enabled agent job 116539284201 verified rejected activation restored
its prior runtime and retained queue. The exact historical sample was delivered
after real rollback. Verification completed 136 tasks with zero failures and
two expected rescues. No host admission, external VPN or real Telegram result
is inferred from these isolated successes.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.

## Full source gate coverage

Independent inspection mapped every substantive `make check` consumer to the
unchanged CI workflow. Completion requires each selected job to succeed:

| Gate | Observed source consumer |
|---|---|
| Task/OpenSpec, secret scans | task-contract; local full-history and final staged gitleaks |
| Terraform fmt/validate/test, policies | Four provider jobs, Conftest and native bootstrap lifecycle |
| Ansible lint/syntax, YAML/shell/Actions | Ansible, yamllint, shellcheck, actionlint and zizmor jobs |
| Cloud-init and MTProto helper | Actual schema container and Go test jobs |
| Render, secrets/schema/bundle, snapshots | Python validators and complete portable collection |
| AWG version floor and deploy profiles | Actual repository validator CLI and guard tests in portable collection |
| Portable regressions and shell lifecycle | All four disjoint pytest shards plus aggregate; Bats |
| CLI package/dependencies/lint/test/parity | Reusable vpnd jobs, including Mac runners |
| Liveness/promtool and runtime | Actual pinned parsers plus native integration/runtime acceptance |

Hosted event-range scanning does not replace local history scanning: the latter
scanned all 2,311 commits / 41.94 MB and found no leaks. Final staging is scanned
separately before committing. Targeted Mac tests and runtime results remain
recorded individually; the failed monolithic invocation is retained as failed.

## Final source acceptance (2026-10-15)

All unchanged hosted source consumers and native acceptance passed in CI 38768887914 on `f6ad803e97237d8d8ec3839284d84db974ea986c`. Focused Mac validation, snapshots and full-history secret scanning passed as recorded above. The owner-approved task scope accepts this combined source gate; the failed monolithic Mac invocation is not reclassified as passing. No external infrastructure or human notification receipt is claimed.

## Observed integrated M1 results (2026-10-15; passed)

The following are actual observations from main CI `38792726270` on
`3010dfb517b84cd7fbe9c3512b30b87d63b64fe8`, separate from the retained
premerge evidence. All 88 CI jobs passed without failed, cancelled, skipped
or pending jobs. CodeQL run `38792726004` passed both jobs with zero open
repository alerts. Transport runtime acceptance job `116621390735` and the
final aggregate passed; complete current source acceptance is observed.

Canonical enabled collector job `116621391330` replayed all 42,000
current/historical/churn samples with ten fixture node labels and 2,000
base series each, including 86,400-second history. Exact per-sample values
and original timestamps passed. Replay took 21.130900467 seconds; collector
MemoryPeak was 189,906,944 bytes and allocated storage was 1,757,184 bytes.
Observed cumulative CPU usage was 8,220,762 microseconds and throttling was
38,441,429 microseconds across 267 throttled periods. Resource ceilings
were unchanged; replay had no OOM, queue loss or unexpected restart, and
public nginx identity remained unchanged. Clean/abrupt historical restart
and filesystem latch tests also passed. This bounded workload does not
establish seven-day capacity or ten independently enrolled hosts.

Enabled agent job `116621391025` delivered the exact historical sample
after actual rollback; verification observed 136 tasks, 14 changes, zero
failures and two expected rescues.

Kuma job `116621392357` verified the checksum and version of pinned age
v1.3.2 and ran the actual pinned rootless observer at 512 MiB / 0.25 CPU.
Valid push acknowledgement and unknown-token refusal passed. Node
missing-signal detection was 120.908–122.002 seconds, never-started was
120.007 seconds and delivery was 541.003 seconds. Authenticated monitor
persistence after restart, quiesced age-encrypted backup, authenticated
isolated restore and owned cleanup all passed. Restored notifications were
blocked by `network=none`. No real Telegram delivery or human receipt is
implied. Isolated runtime evidence belongs to remote_ci/artifact; external
staging remains not applicable from this task's creation.
