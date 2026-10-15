---
task_id: MON-1792080593038468
change: mon-1792080593038468-isolated-resource-bounded-monitoring
commit_sha: "f6ad803e97237d8d8ec3839284d84db974ea986c"
local: "passed"
local_evidence: "139 focused monitoring cases plus final 32 resource cases, 56 workflow/resource cases, 163 snapshots and production-profile lint passed. Local full-history gitleaks scanned 2311 commits with no leaks. Full local make check failed on registry timeout; queued retry cancelled; unchanged full source CI passed."
remote_ci: "passed"
remote_ci_evidence: "CI 38768887914 completed all 88 jobs successfully on f6ad803e97237d8d8ec3839284d84db974ea986c; complete native integration, AWG, XHTTP, runtime rollback and canonical monitoring scenarios passed. Required CodeQL checks succeeded on this source."
dry_run: not_applicable
dry_run_evidence: "Source-only task created after owner decision 2026-10-15; no external-host check mode is in scope."
staging: passed
staging_evidence: Canonical enabled collector and agent plus pinned network-isolated Kuma runtime succeeded on source f6ad803e97237d8d8ec3839284d84db974ea986c in CI 38768887914.
live: not_applicable
live_evidence: "Source-only task; external deployment, real Telegram/human receipt and cutover are excluded, not passed."
client: not_applicable
client_evidence: "Live authenticated VPN performance is excluded; isolated runtime traffic does not claim external client acceptance."
artifact: "passed"
artifact_evidence: "All 163 golden snapshots match; source schemas contracts and redacted exact-runtime acceptance artifacts passed."
---

# Verification

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
