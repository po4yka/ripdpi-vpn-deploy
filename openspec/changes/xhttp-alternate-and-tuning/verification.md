---
task_id: "XRY-1791617991738391"
change: "xhttp-alternate-and-tuning"
commit_sha: "e30d591f0c0af7f43283a7abaa68c68e9fe0ed00"
local: "blocked"
local_evidence: "824933e0: 485 affected portable tests, complete 69-test sentinel suite, 112 endpoint/check-mode tests, 163 snapshots, exact parser checks and make validate passed. Full make check reached Terraform test initialization and failed on a registry timeout; a later repeat passed Terraform and all pre-suite checks, but setup of 62 AWG tests failed because HOME-isolating fixtures resolved an inactive SOPS shim. Direct installed SOPS/age paths fixed the invocation: the complete 62-test module passed. The corrected full repeat exhausted the standard 3600-second machine gate wait and exited 75 before execution; no full-gate pass is claimed."
remote_ci: "required"
remote_ci_evidence: "Frozen e30d591f passed all 89 CI jobs, CodeQL and documentation workflows. Incoming remote commit 27185226 subsequently merged main TLS/WARP fixes (52d73286); current merged-head CI has not been observed and remains required."
dry_run: "not_applicable"
dry_run_evidence: "source capability is exercised in isolated local/native runtime; no real inventory run is part of this task"
staging: "passed"
staging_evidence: "824933e0 archived source: complete disconnected Linux arm64 make test-xhttp-delivery-matrix passed all 10 cases in 629.60 seconds; comparative native traffic, primary outage, TLS refusal, resource bounds and restored baseline. No external staging soak."
live: "not_applicable"
live_evidence: "no production rollout is part of this source or disabled-default feature task"
client: "passed"
client_evidence: "824933e0: checksum-verified native Xray 26.3.27 fixture processes completed authenticated primary/alternate and upload/download cases for auto, packet-up and stream-up; wrong TLS/credentials refused. No physical or external client acceptance."
artifact: "passed"
artifact_evidence: "824933e0: 163 golden renders and complete emitted native profiles parsed before real traffic; selected credentials stay in private fixture documents and endpoint evidence excludes UUIDs/keys. Raw technical measurements are retained in the complete native target output."
---

# Verification

## Requirement evidence

The source SHA above is frozen. The local native command ran from its git archive in an owned disconnected Linux arm64 container. Staging/client categories describe only that local harness and its native fixture processes under the authorized scope. The XHTTP runtime/source files remain identical to 824933e0; 35dd2dfb changes only the native job total time budget, and e30d591f adds task evidence. Hosted CI is complete for frozen e30d591f; the later incoming main integration requires fresh current-head CI. Local full-gate evidence remains blocked: the corrected invocation could not obtain a machine build slot within its standard 3600-second bound.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-XAT-ALTERNATE | XRY-1791618003859679 | 824933e0: complete 10-case native matrix (distinct TLS identity, primary outage, wrong certificate/credentials) plus selected-device admission tests. | passed |
| REQ-PROTO-XAT-ALTERNATE | XRY-1791618006858260 | 824933e0: complete 10-case native matrix (distinct TLS identity, primary outage, wrong certificate/credentials) plus selected-device admission tests. | passed |
| REQ-PROTO-XAT-ALTERNATE | XRY-1791618008836301 | 824933e0: complete 10-case native matrix (distinct TLS identity, primary outage, wrong certificate/credentials) plus selected-device admission tests. | passed |
| REQ-PROTO-XAT-TYPED | XRY-1791618006858260 | 824933e0: complete native mode and bounded-pool matrix at limits 1, 2, 4; schema/semantic boundary and literal Make input tests; unsupported recipient/version/retirement controls refuse. | passed |
| REQ-PROTO-XAT-TYPED | XRY-1791618008836301 | 824933e0: complete native mode and bounded-pool matrix at limits 1, 2, 4; schema/semantic boundary and literal Make input tests; unsupported recipient/version/retirement controls refuse. | passed |
| REQ-PROTO-XAT-MEASURED | XRY-1791618007864586 | 824933e0: exact 1 MiB per direction, both unconstrained and identical 2 ms / 20 Mbit paths, idle, reconnect, RSS/socket observations and baseline restoration; all declared thresholds passed. | passed |
| REQ-PROTO-XAT-MEASURED | XRY-1791618008836301 | 824933e0: exact 1 MiB per direction, both unconstrained and identical 2 ms / 20 Mbit paths, idle, reconnect, RSS/socket observations and baseline restoration; all declared thresholds passed. | passed |
| REQ-PROTO-XAT-ROLLBACK | XRY-1791618003859679 | 824933e0: native guarded destination and public-log privacy assertions, parser/certificate candidate refusal, unchanged accepted bytes and authenticated baseline restoration; static security review approved. Full gates remain separate pending categories. | passed |
| REQ-PROTO-XAT-ROLLBACK | XRY-1791618007864586 | 824933e0: native guarded destination and public-log privacy assertions, parser/certificate candidate refusal, unchanged accepted bytes and authenticated baseline restoration; static security review approved. Full gates remain separate pending categories. | passed |
| REQ-PROTO-XAT-ROLLBACK | XRY-1791618008836301 | 824933e0: native guarded destination and public-log privacy assertions, parser/certificate candidate refusal, unchanged accepted bytes and authenticated baseline restoration; static security review approved. Full gates remain separate pending categories. | passed |

## Observed local acceptance

- `make test-xhttp-delivery-matrix`: 10 passed, no selected skips, exact source archive, isolated Linux arm64, Xray 26.3.27 and Hysteria 2.13.0 verified against pinned archive/binary checksums. This is an owned local lab, not an external deployment.
- Complete affected portable selection: 485 passed. The complete sentinel suite separately passed 69 tests after serializing its fixed-loopback-port fixtures. Endpoint/check-mode selection: 112 passed. One existing collection SyntaxWarning is retained.
- `make validate`: passed (four Terraform roots, history/staged gitleaks, ansible-lint and playbook syntax); absent inventory warnings are expected in this credential-free worktree.
- `make task-check snapshot-check`: passed; 163 golden templates unchanged. `make liveness-profile-check`: passed with exact Xray 26.3.27 and checksum-verified sing-box 1.14.3 supplied through an invocation-local PATH.
- The first parser attempt correctly refused the workstation's unrelated sing-box 1.13.16; the global installation was preserved. Initial parallel sentinel attempts conflicted on fixed fixture ports; only owned orphan fixture processes were removed, and the complete suite passed serially.
- The rejected request/age-retirement experiment retained 43 live sockets for a nominal two-client pool. The admitted profile fixes retirement to zero and limits tuning to stream-up. The resource assertions were retained; the accepted configurations satisfy them at 1, 2 and 4.

## Exact-source measurements

All rows sent and received exactly 1 MiB; times and memory are measured technical observations. These are local regression bounds, not fleet throughput or long-duration capacity claims.

| Configured pool | Live frontend sockets | Client RSS KiB | Candidate MiB/s | Constrained candidate / baseline MiB/s | Restored baseline MiB/s |
|---|---|---|---|---|---|
| 1 | 1 | 34016 | 0.3270 | 0.1136 / 0.1130 | 0.3554 |
| 2 | 2 | 34008 | 0.3423 | 0.1103 / 0.1112 | 0.3457 |
| 4 | 4 | 34172 | 0.3601 | 0.1135 / 0.1093 | 0.3299 |

## Security review

APPROVE. Reviewed the complete source range and all staged/unstaged/untracked paths. Native recipient listeners bind loopback, unmatched routing is blackhole, exact selected-device identities remain private, unrecognized tuning refuses, and no server listener, provider object, credential authority, production pin, P0 shape or PQE HOLD transition is added. Public transport logs and redacted liveness evidence retain the native privacy assertions. Production enablement remains outside this local source change.

## Remaining completion gate

The full-gate execution step remains open and the portfolio item is blocked on local machine build capacity. Resume `build-gate -- make -j1 check` with the pinned parser binaries available, observe terminal exact-source CI, then complete the review-state commit and taskctl archive/close lifecycle. Never infer full-gate success from the passing native XHTTP selection. The corrected local repeat exited 75 after waiting 3600 seconds before execution; no unattended deployment or test run remains from this task.

## Hosted acceptance

[Exact-source CI run](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38902283925): all 89 jobs passed for e30d591f, including both native transport acceptance partitions, every selected Molecule role, all portable test partitions, Terraform tests/policies, secret scanning and package checks. The native runtime job passed its complete sequence in approximately 30 minutes, including the 10-case XHTTP matrix; the increased 40-minute total budget preserves each per-test assertion.

## Incoming main integration

Before publishing the final evidence update, a normal push was rejected because remote commit 27185226 had integrated main commit 52d73286 (TLS transcript and WARP teardown fixes). Those incoming changes are preserved by a normal merge without rewriting history. They do not change the XHTTP implementation, but the 89-job result above applies to e30d591f only. Current merged-head CI remains required; neither that integration nor metadata updates are claimed to have completed a fresh full gate.
