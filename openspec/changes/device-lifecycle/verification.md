---
task_id: OPS-1792679812321846
change: device-lifecycle
commit_sha: null
local: required
local_evidence: 368 portable lifecycle/schema/publisher/barrier tests passed; review boundary fixes passed targeted SOPS/TLS and IO checks. Full make check remains pending.
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Exact private manifest, Make literal dispatch, check-mode runtime projection and typed revocation extra-vars tests passed.
staging: not_applicable
staging_evidence: Source implementation only; no staging deployment authorized.
live: not_applicable
live_evidence: No live fleet or private credential operation is authorized.
client: required
client_evidence: Real isolated native positive and denied credential paths required; no physical-device claim.
artifact: required
artifact_evidence: Real SOPS issuance, all-grant refresh, private native output, output collision and lost publication acknowledgements passed.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEVICE-OPERATION-PLAN | OPS-1792680221456320 | Complete declared inventory, retained publishers, source/input fences and real encrypted authority tests passed | passed |
| REQ-DEVICE-OPERATION-ISSUE | OPS-1792680221456320 | Usable encrypted issuance and private AWG/Naive artifacts passed; isolated native execution pending | partial |
| REQ-DEVICE-OPERATION-REFRESH | OPS-1792680223324164 | Actual publisher CAS and TLS grants preserve URLs/expiry; lost acknowledgement and private output tests passed | passed |
| REQ-DEVICE-OPERATION-REVOKE | OPS-1792680222031123 | Portable forward recovery, real TLS 200-to-410, grant-only all-node adoption and name-collision tests passed; Linux native execution pending | partial |
| REQ-DEVICE-OPERATION-RESUME | OPS-1792680222634877 | Real SOPS/publisher lost acknowledgements, immutable revocation intent and SIGKILL barrier tests passed | passed |

Step OPS-1792680223917464 owns complete local gates, independent review and
protected PR/exact-main CI. No unfinished or refusal-only path closes the task.


Independent review found and corrected grant-only revocation admission, P0-only
retained profile rendering and exact canary ownership for a real device sharing
its internal client name. Root fixes received follow-up read-only review.
Portable evidence does not claim physical-device or production acceptance.
