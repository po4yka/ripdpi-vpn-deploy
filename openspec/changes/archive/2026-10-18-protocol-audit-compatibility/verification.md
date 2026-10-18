---
task_id: XRY-1792265213021342
change: protocol-audit-compatibility
commit_sha: 4f7b54e4480039526d9c8febca033932506f4a56
local: passed
local_evidence: 'Canonical make check completed with exit 0 at fa3433719de3ea21674c68529bed15e34e395fa4: 7957 portable tests, 45 subtests, 65 Bats tests, 322 vpnd tests, complete transfer coverage for 206 baseline functions and ci-fast OK. Later docs/package and 95 fixture/emitter cases passed separately; see revision provenance below.'
remote_ci: passed
remote_ci_evidence: Source CI 39113178648 passed all 92 jobs at fbfc7af8875498700a9cf4c46efc8c7d0484b667. Accepted main 4f7b54e4480039526d9c8febca033932506f4a56 has the same tree; main CI 39117467457 passed all 92 jobs, including required gate 117657754950, with no failures, skips or cancellations.
dry_run: not_applicable
dry_run_evidence: Credential-free synthetic checks only. No real inventory or deployment transaction is part of this source task.
staging: not_applicable
staging_evidence: No staging resource or promotion is part of this source task.
live: not_applicable
live_evidence: No VPN node, provider or private fleet operation is part of this source task.
client: passed
client_evidence: Native job 117634643569 passed 164 native cases, including two Naive, six P0 and 12 Snell cases, plus actual AWG, Hysteria ECH, XHTTP and authenticated topology targets. All five acceptance/recovery jobs and main native job 117646103359 passed. Pinned real engines use synthetic local clients; no fleet, physical-device or Telegram acceptance is claimed.
artifact: passed
artifact_evidence: Official checksummed mtg archive/parser, migration, invalid-candidate preservation, idempotence and all 164 snapshots passed. Reproducible package/install/rollback passed after docs integration. Both agreed public fixture blobs and all 31 contract files match the accepted client contract. PR329 main 4f7b54e4480039526d9c8febca033932506f4a56 has the exact tested fbfc7af8 tree.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTOCOL-MUX | XRY-1792265286038091 | Native job 117634643569 passed all six P0 cases, including authentication, XUDP, Vision, Mux.Cool and typed Finalmask controls | passed |
| REQ-PROTOCOL-MTG | XRY-1792265286826282 | CI 39113178648 and main CI 39117467457 passed official archive/parser checks, legacy receipt migration, invalid-candidate preservation and idempotence | passed |
| REQ-PROTOCOL-IDENTITY | XRY-1792265286826282 | Complete local and hosted admission suites passed; 95 affected bundle/emitter tests and both validators passed; all 31 contract files match client fdc42a19f8701216b727f76ab5dc7fd5b73abcde | passed |
| REQ-PROTOCOL-NAIVE | XRY-1792265287536541 | Native job 117634643569 passed actual handler 502 control, canonical logging, HTTP/2 reset, authentication and independent revocation | passed |
| REQ-PROTOCOL-PQE | XRY-1792265286826282 | PQE HOLD remains enforced; release-history corrections, all 164 snapshots and complete admission suites passed | passed |
| REQ-PROTOCOL-NATIVE | XRY-1792265287536541 | Native job 117634643569 and all five separate acceptance/recovery jobs passed with real pinned engines; main CI 39117467457 also passed all native jobs | passed |
| REQ-PROTOCOL-INVENTORY | XRY-1792265288315040 | Both CRLF regressions changed from fail to pass; 35 renderer/topology tests, real Base64 1.5 in both modes and complete local/hosted gates passed | passed |
| REQ-PROTOCOL-TEST-LIFECYCLE | XRY-1792265288315040 | Real no-client subprocess regression changed from fail to pass; all 14 update-cache tests, 322 local vpnd tests and all four hosted platforms passed | passed |

## Accepted source and local evidence

PR324 merged as a620c9dfb0ef41e13410a932016d88ec6785b66d after CI 39070456406
passed all 92 jobs at a15e77ad71e699a5663009bd8bcbaff844975811. Those two trees
were equal. PR329 then merged as 4f7b54e4480039526d9c8febca033932506f4a56.
Its tree equals tested source fbfc7af8875498700a9cf4c46efc8c7d0484b667 exactly.
Source CI 39113178648 and main CI 39117467457 each passed all 92 jobs, with no
failed, skipped or cancelled job. Main required gate 117657754950 passed.

The unchanged canonical make check completed with exit 0 at
fa3433719de3ea21674c68529bed15e34e395fa4. It passed 7957 portable tests,
45 subtests, 65 Bats tests, 322 vpnd tests, lint/type checks and transfer coverage
for 206 baseline functions. Its final line was ci-fast: OK. The 226 native
marker deselections define the local portable scope; hosted native jobs provide
the separate engine and traffic evidence.

Later integration at 049c5c22 passed task contracts, seven instruction tests,
14 documentation tests and the real reproducible package/install/rollback
check. The next delta reused exactly two public fixture blobs from
cc6e171e9edfe8555bbc7800aa584e8a571a865c. Only four synthetic peer public-key
and preshared-key literals changed. Both validators and all 95 affected
bundle/emitter tests passed, including the pinned sing-box parser. A fresh
Git-blob comparison matched all 31 contract files against client
fdc42a19f8701216b727f76ab5dc7fd5b73abcde. Fresh hosted contract-sync also passed.
The schema and cohort fingerprints did not change.

The full make check ran at fa343371. The later documentation and fixture
checks cover the stated deltas. Accepted main 4f7b54e4 has the complete tested
fbfc7af8 tree; the local full command is not attributed to those later hashes.

## Native scope and review

Native job 117634643569 passed the actual target counts 1, 10, 13, 164, 10,
4, 167 and 10: warm AWG, dual-stack AWG twice, Hysteria ECH, the native suite,
XHTTP endpoints/delivery and authenticated topology probes. The native suite
included two Naive, six P0 and 12 Snell cases. Main native job 117646103359
also passed. These are pinned real engines with synthetic local clients;
fleet, physical-device and Telegram reachability are outside this source task.

Independent security reviews approved the production and fixture changes.
Structured reviews accepted the CRLF and update-cache repairs at 0.94 and 0.93;
the actual added fixture diff passed at 0.99. An earlier empty review bundle
was discarded and replaced by that nonempty review.

CodeQL alerts 1296-1300 were reviewed as false positives: their inputs are
public synthetic FakeTLS literals or invalid test values in an automatically
cleaned private temporary directory. They do not read operator credentials or
SOPS material. Alert 1301 records intentional test-relay teardown. Independent
payload, authentication, refusal and reuse checks detect protocol failures.
No query, threshold or broad exclusion changed; the six related threads resolved.

## Local recovery history

Host storage exhaustion initially blocked Docker. Only inactive generated
caches and intermediates were removed after ownership, open-file and process
checks. Source, installed application packages and named reports were retained.
Other host capacity changes occurred independently and are not attributed to
this task's cleanup.

One Docker Desktop launch terminated two active Android emulators through its
backend startup cleanup. The same virtual devices and ports were restored
without data reset; their RAM state was lost. No compiler process was signalled.
Later recovery retained the existing backend and restored emulator processes.
An actual container write probe and the canonical cloud-init check passed.
This incident prevents a claim that all active work was unaffected.

An earlier full gate ended with 7883 passed and 19 failed portable tests.
Installing real flock 0.4.0 resolved 18 failures; both complete watchdog files
then passed all 30 tests. The TLS fixture failure did not recur in three focused
runs or the final full gate. Trust checks and deadlines were retained.
A later gate was interrupted after 4036 passing tests to fix the confirmed
unbounded update-cache fixture; its exit 130 was not a successful gate.
The earlier Intel CI timeout narrowed the stall to that test file but did not
capture its exact test or stack. The final full local and hosted gates passed.

No deployment, VPN node/provider operation, private fleet inventory, real
Telegram connection or operator-secret operation ran.
