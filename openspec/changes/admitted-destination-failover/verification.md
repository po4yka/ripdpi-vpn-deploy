---
task_id: SEC-1792678909985498
change: admitted-destination-failover
commit_sha: null
local: required
local_evidence: Complete destination-boundary and failover suites passed 88 tests; full make check remains required.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No inventory, Ansible task, configuration schema or deployment invocation changes; this scope is the installed Python helper implementation.
staging: not_applicable
staging_evidence: No staging deployment is requested or claimed; a later runtime rollout uses the existing guarded deployment workflow.
live: not_applicable
live_evidence: No real node or provider mutation is authorized by this source implementation.
client: not_applicable
client_evidence: No Android client code changes; owned local SOCKS clients exercise server helper behavior under local evidence.
artifact: not_applicable
artifact_evidence: Python source is installed by the existing role; this change does not produce a separately published binary artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RDB-FAILOVER | SEC-1792679160742251 | `test_transport_destination_boundary.py` and `test_candidate_order_deduplicates_and_keeps_both_families_before_cap` | Passed in the complete 88-test run |
| REQ-PROTO-RDB-FAILOVER | SEC-1792679161411775 | `test_transport_destination_failover.py` real sockets: IPv4/IPv6 positive cases, third-candidate success, exact eight-attempt and two-open-socket caps, shared deadline and post-deadline closure | Passed in the complete 88-test run |
| REQ-PROTO-RDB-COMMIT | SEC-1792679162099578 | Both complete files cover exact winner-only pipelined bytes, no retry after reset, abrupt controls, cancellation/stop cleanup, restored capacity and existing UDP behavior | 88 passed; full local and hosted gates remain required |

## Required commands

- `mise exec -- python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_destination_failover.py --fail-on-skip`.
- `./taskctl openspec cli validate admitted-destination-failover --strict`.
- `make task-check` and `build-gate -- mise exec -- make check`.
- Required hosted PR checks on the exact reviewed implementation revision.

The local gateway is an owned SOCKS fixture that makes actual destination socket
connections. It is not a deployed Xray/Hysteria gateway. Positive source behavior,
complete local gates and required hosted checks must be observed before this task
can close; refusals, fixture-only claims and omitted cases do not qualify.

## Observed source review

The complete committed, staged, unstaged and untracked change was inspected.
No new listener, policy exception, DNS re-resolution, credential output, runtime
dependency or cross-layer mutation was introduced. Required full local and hosted
checks remain outstanding; this review does not assert deployment acceptance.
