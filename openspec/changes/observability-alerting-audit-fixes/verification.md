---
task_id: MON-1791825755591250
change: observability-alerting-audit-fixes
commit_sha: 7530044cb24a9cf40197d55fe96b3d0ec61ed9ef
local: required
local_evidence: Current fixture and bounded-I/O repair requires a renewed complete gate. The recorded prior full pinned-toolchain build-gated make check at 7d3b74cbbfa8acc5bef0cf28698af4cbe4117d5e passed 6491 portable tests, 22 subtests, 57 Bats cases, 303 CLI tests, validation and lint/parity. All commit hooks passed. An initial registry-metadata network failure was followed by a successful five-package dependency check and the complete passing gate.
remote_ci: required
remote_ci_evidence: Current source requires exact-head checks. Recorded prior frozen source 7d3b74cbbfa8acc5bef0cf28698af4cbe4117d5e completed 92 successful checks and one neutral optional image scan; all nine current branch-required contexts passed. Selected native runtime, monitoring-role failure/recovery and full-stack checks passed.
dry_run: not_applicable
dry_run_evidence: No real inventory or SSH transaction is authorized.
staging: not_applicable
staging_evidence: Source-only repair; disposable local role validation is not staging acceptance.
live: not_applicable
live_evidence: Deployment and real Telegram messages are explicitly excluded.
client: not_applicable
client_evidence: No authenticated physical-client or VPN performance acceptance is claimed.
artifact: passed
artifact_evidence: Repository-local implementation, regression tests and frozen-source check results are recorded below; source-only changes do not authorize deployment or real notification traffic.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ALERT-URL | MON-1791825842898373 | Executable producer/consumer regressions, pinned rules, snapshots and complete local gate passed; exact-source native runtime and role scenarios passed | passed |
| REQ-ALERT-RESPONSE | MON-1791825842898373 | Executable producer/consumer regressions, pinned rules, snapshots and complete local gate passed; exact-source native runtime and role scenarios passed | passed |
| REQ-WATCHDOG-PRIVATE | MON-1791825843454772 | Executable producer/consumer regressions, pinned rules, snapshots and complete local gate passed; exact-source native runtime and role scenarios passed | passed |
| REQ-EVIDENCE-TYPED | MON-1791825843454772 | Executable producer/consumer regressions, pinned rules, snapshots and complete local gate passed; exact-source native runtime and role scenarios passed | passed |
| REQ-EVIDENCE-EXPIRY | MON-1791825843454772 | Executable producer/consumer regressions, pinned rules, snapshots and complete local gate passed; exact-source native runtime and role scenarios passed | passed |
| REQ-TARGET-PRESENCE | MON-1791825843454772 | Executable producer/consumer regressions, pinned rules, snapshots and complete local gate passed; exact-source native runtime and role scenarios passed | passed |
| REQ-UNIT-PRESENCE | MON-1791825843454772 | Executable producer/consumer regressions, pinned rules, snapshots and complete local gate passed; exact-source native runtime and role scenarios passed | passed |
| REQ-OBSERVER-RECOVERY | MON-1791825844021163 | Atomic intent publication, pre-stop failure and process-interruption regressions passed in the complete local gate; selected native observer recovery checks passed at the frozen source | passed |
| REQ-CANARY-ACK | MON-1791873973944403 | 53 portable relay tests include ambiguous edit, restart and preflight persistence regressions | passed |
| REQ-OPERATOR-DRILL | MON-1791873974708567 | 97 operator tests include actual relay parser and exact receipt rejection paths | passed |
| REQ-QUEUE-ORDER | MON-1791825843454772 | Seven pinned receiver/readiness regressions passed; exact historical identity, strict and finite-window rejection assertions remain intact; frozen-source native sender recovery passed | passed |
| REQ-SOURCE-VALIDATION | MON-1791825844572081 | Prior frozen source passed; current fixture and bounded-I/O repair requires renewed full local and exact-head hosted checks | required |

## Repository-local implementation evidence

- [Observer backup and recovery implementation](../../../ansible/roles/observability_kuma/files/observability-kuma-backup.py) and [its executable regressions](../../../tests/unit/test_observability_kuma.py) cover the private marker, actual process termination and subsequent recovery boundaries.
- [Role lifecycle contract](../../../ansible/roles/observability_kuma/CLAUDE.md), [observer interruption verification](../../../ansible/roles/observability_kuma/molecule/default/verify.yml) and [the alerting requirements](specs/operations/observability-alerting-reliability/spec.md) define the source-only acceptance limits.
- This document records frozen commits and observed check outcomes directly. External review URLs and discussion identifiers are not evidence in the tracked artifact.

## Frozen baseline acceptance

Source `0c29515c99b4a916e85d3df028efab016b9230b8` completed all reported checks: 92 successful and one neutral optional image scan. The nine required contexts were successful: dependency selection, task contract, Python validators, Python unit tests, shell checking, secret scanning, Python security analysis, automation security analysis and their aggregate gate. Native observer forced-death and actual start-deadline recovery passed. Independent source/security review approved without actionable P0-P2 findings.

Client contract integration at commit `7108f7ac5dc8b2457de403b99455e58714825bc7` followed 37 successful selected checks, 60 local fixture tests, schema validation, architecture health and locked dependency metadata. All 31 non-documentation contract files matched the frozen server source. Both the dedicated and parent-workflow contract comparisons passed.

## Native fixture caveat

The enabled agent historical-delivery assertion failed twice at source `2095269dcfd0b401a5f863e2c461b9dd63dfe54a`. Instrumented source `cf9e147e8149da348bbc5ba1293a4bbe2a57ccd4` showed empty historical and recent probe results, 3937 retained queue bytes, zero queue/sample drops, 14 fixture receiver errors and forwarding retries. That instrumented run did not establish a cause. Frozen baseline `0c29515c99b4a916e85d3df028efab016b9230b8` preserved forwarding, assertions and retries and passed the native scenario; fixed bounded failure categories remain available. The later failure at `f15e3ff3232eeac51e7633800a74a06a81fc8b36` recorded HTTP 400 responses and out-of-order samples. The current repair sets the collector out-of-order window to its existing retained-history duration. A real pinned receiver test proves that mixed older batches fail with the former strict policy, preserve the exact historical sample with the bounded window, and still fail beyond that window. Selected native sender recovery passed at frozen source `7d3b74cbbfa8acc5bef0cf28698af4cbe4117d5e`; measured late-history resource admission remains a separate rollout gate.

Local amd64 emulation failed before changed runtime paths and is not native acceptance. Source/CI results do not establish deployment, authenticated physical-client performance or human receipt. No deployment or real Telegram messages are authorized.

## Review corrections

Restart intent is staged privately, fully written and fsynced before atomic same-directory publication and directory syncing. Ordinary pre-publication failures retire only the owned staging file; forced death can leave an ignored private candidate. The active observer is not stopped before intent is durable, and a complete published marker supports recovery after a directory-sync failure. Retained canonical intent remains unchanged.

The verification artifact uses only repository-local source links, frozen revisions and recorded check outcomes. Atomic-publication regressions, independent review and exact-source CI results passed at the frozen source. Receiver readiness retries only expected startup failures within its existing deadline; unexpected errors propagate and all failure paths retire their owned pinned process. The active contracts distinguish one-worker concurrency from replay order and define the finite admission window relative to the global TSDB maximum timestamp.

## Current completion checks

The audited repairs include bounded producer URLs and upstream response bodies, evidence expiry, observer recovery, drill delivery receipts and durable canary attempt sequences. Frozen source `7d3b74cbbfa8acc5bef0cf28698af4cbe4117d5e` passed the complete pinned-toolchain local gate with 6491 portable tests, 22 subtests, 57 Bats cases and 303 CLI tests, plus validation and lint/parity. The initial metadata fetch failed on network routing; its isolated dependency retry and the complete renewed gate passed without changing or weakening validation. Independent review approved the follow-up with no actionable P0-P2 findings.

The frozen source completed 92 successful hosted checks and one optional neutral image scan, with no failed or pending checks. All nine current branch-required contexts passed, including the aggregate gate and both source-analysis contexts. Selected native Linux checks confirmed historical queue replay and observer interruption recovery. No deployment or real Telegram message was sent. Small reordered-batch tests do not establish seven-day replay capacity; measured late-history resource admission and live/human acceptance remain required by the separate rollout contract.

## Current local gate follow-up

The first local rerun passed 6449 portable tests and 22 subtests; group ownership and isolated Ansible fixture repairs addressed its 38 failures. The next run passed 6480 portable tests and 22 subtests, including all 12 authority variants, but found seven failures. Complete focused reruns passed 83 release/transition, 159 cascade/deploy, 140 fleet/operator and 12 bootstrap I/O tests. The repairs preserve production deadlines, byte limits, ownership and signal refusals. Transient nonblocking pipe backpressure retries within the existing deadline; group cleanup retries permission refusal only after an exited child is reaped. Final structured and independent review passed. The complete renewed local gate and exact-head CI remain required for these changes. No deployment or real Telegram message was sent.
