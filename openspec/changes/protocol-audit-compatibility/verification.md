---
task_id: XRY-1792265213021342
change: protocol-audit-compatibility
commit_sha: a15e77ad71e699a5663009bd8bcbaff844975811
local: blocked
local_evidence: Focused identity/admission (37), authenticated probe (48), image-pin/cloud-init (29), Naive/Snell (43), real Snell wire (6) and template snapshot (164) checks passed. The exact Caddy Fast Open control and its negative logging mutation passed locally. Full make check passed task-check and validate, then failed at cloud-init schema with Docker fallback timeout 125; container cleanup remains unverified. The aggregate local gate did not pass.
remote_ci: passed
remote_ci_evidence: CI run 39070456406 passed all 92 jobs at a15e77ad71e699a5663009bd8bcbaff844975811. All four portable shards passed 7769 tests; required checks job 117518733836 and both CodeQL language scans passed. Both unchanged Trivy scans, all Molecule jobs and every native acceptance/recovery job passed.
dry_run: not_applicable
dry_run_evidence: Source-only repair with synthetic role rendering; no deployment controller or private deployment run.
staging: not_applicable
staging_evidence: Optional roles remain disabled; no rollout or promotion is part of this source task.
live: not_applicable
live_evidence: No real node, provider, inventory or credential operation is part of this task.
client: passed
client_evidence: Native integration job 117507132861 passed all 156 integration cases, including six P0 and six Snell wire cases and Naive authenticated CONNECT, actual handler 502 control, HTTP/2 reset and retained-log privacy. Its following targets passed 14 XHTTP cases, 167 topology cases and six AWG dual-stack cases. These use real pinned engines and synthetic local clients; they are not fleet or Telegram acceptance.
artifact: passed
artifact_evidence: The official checksummed mtg archive, native parser, legacy immutable receipt migration, rejected-candidate preservation and idempotence passed in CI 39070456406. Template rendering and all 164 snapshots passed. PR324 merged as a620c9dfb0ef41e13410a932016d88ec6785b66d; git diff between that merge and tested source a15e77ad71e699a5663009bd8bcbaff844975811 was empty.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTOCOL-MUX | XRY-1792265286038091 | Run 39070456406, job 117507132861; all six P0 authentication, XUDP, Vision, Mux.Cool and typed Finalmask cases passed | passed |
| REQ-PROTOCOL-MTG | XRY-1792265286826282 | Run 39070456406; official archive/parser, legacy migration, invalid-candidate preservation and idempotence passed | passed |
| REQ-PROTOCOL-IDENTITY | XRY-1792265286826282 | Local 37 admission cases and all four final CI portable shards passed | passed |
| REQ-PROTOCOL-NAIVE | XRY-1792265287536541 | Job 117507132861; actual handler 502 control, canonical logging, HTTP/2 reset, authentication and independent revocation passed | passed |
| REQ-PROTOCOL-PQE | XRY-1792265286826282 | PQE HOLD remains enforced; corrected release history, all 164 snapshots and final CI admission regressions passed | passed |
| REQ-PROTOCOL-NATIVE | XRY-1792265287536541 | Job 117507132861 and all five separate acceptance/recovery jobs passed with real pinned engines | passed |

## Review and merge

PR324 passed the full exact-head CI and merged through protected squash merge.
The accepted main tree equals the tested source tree. Security review approved
all production changes. Incremental structured reviews reported no actionable
P0-P2 findings; the final Fast Open fixture review accepted the patch at 0.91.

CodeQL alerts 1296-1300 were individually reviewed and dismissed as false
positives. Their only inputs are public synthetic FakeTLS literals and invalid
test values under an automatically cleaned private temporary directory. They do
not read operator credentials, SOPS documents or secret environment inputs.
Alert 1301 was recorded as intentional test-relay teardown, not a code fix.
The next statement retires the failed channel, and independent payload,
authentication, refusal and reuse checks detect protocol failures. No query,
threshold or broad exclusion changed. All six related review threads resolved.

## Remaining local gate

Execution step XRY-1792265288315040 remains open. The unchanged make check command
must pass in a supported healthy environment before local acceptance and archive.
A later five-second Docker listing also timed out, so container cleanup remains
unverified. Hosted Linux success does not change the failed local command into
a pass. The task remains blocked; it is not archived or closed.

No deployment, fleet inventory, real Telegram connection or operator secret
operation ran.
