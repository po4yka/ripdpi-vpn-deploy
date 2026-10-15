---
task_id: MON-1792080593038468
change: mon-1792080593038468-isolated-resource-bounded-monitoring
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: "Source-only task created after owner decision 2026-10-15; no external-host check mode is in scope."
staging: not_applicable
staging_evidence: "No external staging deployment is in scope. Positive isolated runtime acceptance remains required under remote_ci and artifact; it is not host staging evidence."
live: not_applicable
live_evidence: "Source-only task; external deployment, real Telegram/human receipt and cutover are excluded, not passed."
client: not_applicable
client_evidence: "Live authenticated VPN performance is excluded; isolated runtime traffic does not claim external client acceptance."
artifact: required
artifact_evidence: null
---

# Verification

This task starts with source and isolated real-runtime scope, per the owner decision on 2026-10-15. External staging is not applicable from its first protected-main publication; actual isolated runtimes remain required source/CI/artifact evidence. The old task's missing live evidence is not transferred or accepted. Future deployment still requires exact-host resource/private-path/backup admission, credentials, real notifications, human receipt, matched VPN performance and approved cutover.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-IRBO-BOUNDS | MON-1792080763077431 | Canonical enabled collector/agent runtime: restart, saturation, allocated-block latch and isolation | Required current exact-SHA runtime |
| REQ-IRBO-REPLAY | MON-1792080763077431 | New actual managed-sender 42,000-sample, ten-label-node, 24-hour historical replay | Portable producer/verifier checks passed; canonical runtime required |
| REQ-IRBO-PRIVATE | MON-1792080763077431 | Enabled real mTLS ingestion/revoked/wrong-SAN and unchanged public nginx | Required current exact-SHA runtime |
| REQ-IRBO-OBSERVER | MON-1792080764176275 | Actual pinned Kuma acknowledgement, missing/never-started timing, restart persistence, encrypted isolated restore | Required current reproducible runtime evidence |
| REQ-IRBO-DELIVERY | MON-1792080764176275 | Relay/canary/push regressions and actual isolated rule-to-relay receipt | Source checks and canonical scenario required; real messaging excluded |
| REQ-IRBO-MIGRATION | MON-1792080765681879 | Contract/schema/operator obsolete-input tests, snapshots, failed activation/monitoring-only rollback | Required current source and runtime gates |
| REQ-IRBO-SCOPE | MON-1792080765681879 | Coherent task/verification/runbook scope; focused Mac regressions and complete unchanged exact-SHA hosted source/native CI | Required; no live result inferred |

## Observed local checks

- `mise exec -- python3 -m pytest -q tests/unit/test_observability_agent_render.py tests/unit/test_observability_control_plane_render.py tests/unit/test_observability_control_plane_generation.py tests/unit/test_observability_resource_bounds.py`: 139 passed before the additional per-sample-value equality regression.
- Final `mise exec -- python3 -m pytest -q tests/unit/test_observability_resource_bounds.py`: 32 passed, including exact workload rows and rejection of corrupted count, sum, per-sample values and timestamps. These execute fixture helpers, not native services.
- `mise exec -- ansible-lint ansible/roles/observability_control_plane/molecule/enabled/tasks/bounded-runtime.yml`: production profile passed with zero failures/warnings before the final equality assertion; final integrated lint remains required.
- `git diff --check`: passed before final integration.
- Current local Docker is arm64. The exact canonical Debian Molecule image is amd64 and `docker run --rm --network none --entrypoint /bin/sh <pinned-image> -c 'uname -m'` returned `exec format error`. This is a local architecture blocker, not a skipped/passed role gate. Hosted amd64 runtime evidence is required.

## Required remaining gates

- Full source gate, snapshots, task contract and strict OpenSpec validation at the final revision.
- Exact-SHA selected hosted workflows, including canonical `molecule failure (observability_control_plane)` and `molecule failure (observability_agent)` with no selected skips.
- Actual pinned observer timing/persistence/restore runtime evidence; portable mocks and historical claims alone do not accept the new task.
- Final artifacts identify exact source/run revisions and distinguish bounded representative replay from seven-day capacity and real deployment.

Archive remains forbidden while any required category lacks observed complete evidence.
