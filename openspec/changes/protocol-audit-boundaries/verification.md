---
task_id: SEC-1792301529650686
change: protocol-audit-boundaries
commit_sha: a14c339ccf8db8bce10bce5da22380a813a41605
local: passed
local_evidence: Complete make check passed with 7955 portable unit tests and 45 subtests, 65 Bats tests, 321 vpnd tests, 164 snapshots, Terraform tests, policy checks, validators and lint. Exact checksum-verified Xray and sing-box runtimes were used. Independent security and source reviews passed.
remote_ci: passed
remote_ci_evidence: PR CI 39102342981 and exact merged-main CI 39106128582 each passed all 92 jobs. All nine protected contexts passed on the commit_sha with app ID 15368. Strict status checks and administrator enforcement remained enabled.
dry_run: not_applicable
dry_run_evidence: Source repair only; no deployment controller or private inventory operation.
staging: not_applicable
staging_evidence: No staging rollout or optional protocol promotion is included.
live: not_applicable
live_evidence: No provider, host, credential or production operation is included.
client: passed
client_evidence: Real local delivery backend and generated import/QR tests passed. Pinned sing-box 1.14.3 Snell authentication/reuse passed all 12 cases. Linux nginx passed all three privacy/delivery cases and Snell passed all 12 authentication/reuse cases in hosted PR job 117601029863. Certificate controls passed in hosted PR CI 39102342981.
artifact: passed
artifact_evidence: Exact parsed credential values and all per-host metadata pass regression tests. Security-sensitive pins, checks and policy files have no diff.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PAB-LOG | SEC-1792301639236422 | Real nginx unmatched/matching request privacy regressions passed in PR native job 117601029863 | passed |
| REQ-PAB-URL | SEC-1792301639972825 | Real HTTP import/QR byte and header equality; 165 integrated tests passed | passed |
| REQ-PAB-UUID | SEC-1792301641075453 | 14 dedicated tests passed; independent controller refusal precedes mutation | passed |
| REQ-PAB-AWG | SEC-1792301641874277 | 192 admission/binding/version tests passed without skips | passed |
| REQ-PAB-JSON | SEC-1792301642634281 | 229 combined regressions and 12 real Snell authentication/reuse tests passed | passed |
| REQ-PAB-HOP | SEC-1792301643438614 | CLI and materializer refusal tests passed; official sing-box control passed | passed |
| REQ-PAB-SAN | SEC-1792301644239886 | 12 real-certificate operator-script tests passed; uses verify -verify_hostname for OpenSSL 3.0 | passed |
| REQ-PAB-EXTRAS | SEC-1792301645045399 | Multi-host emitted tags and distinct source metadata match | passed |
| REQ-PAB-GATES | SEC-1792301645900459 | Complete make check, independent security/source review and unchanged safety policy passed | passed |

## Integration acceptance

PR 328 merged the reviewed source 2629c3469b0ed917f2c4f51c76fbf2c5d2729031
as the commit_sha. Their Git trees are identical. PR CI 39102342981 and main
CI 39106128582 each passed all 92 jobs. All nine protected contexts passed:
gitleaks, shellcheck, pytest unit tests, codeql (python), codeql (actions),
required checks, task-contract, python validators and CI dependency selection.
The required app ID is 15368. Strict status checks and administrator enforcement
remained enabled. No bypass was used.

The three native nginx privacy/delivery cases and all 12 Snell authentication
and reuse cases passed in PR job 117601029863. Main repeated the full native
suite. This evidence does not establish provider, host or physical-device
acceptance; those operations are outside this source repair.

## Separate release automation

Optional release-please run 39106128487 failed during its GitHub GraphQL
commit-history query with an internal server error. The four previous main
release-please runs passed. This failure did not affect the required code and
protocol checks. Release publication and a release-workflow rerun are outside
this repair.
