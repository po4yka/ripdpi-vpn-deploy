---
task_id: VPD-1787497252303967
change: vpd-1787497252303967-vpnd-probe-matrix-robust-evidence
commit_sha: null
local: required
local_evidence: ""
remote_ci: required
remote_ci_evidence: ""
dry_run: not_applicable
dry_run_evidence: no Terraform surface
staging: required
staging_evidence: ""
live: required
live_evidence: ""
client: blocked
client_evidence: "Schema 3 is withheld from this main candidate until po4yka/RIPDPI synchronizes the vendored probe report schema. Contract-sync run 33079404221 detected the exact mismatch; no gate is bypassed."
artifact: not_applicable
artifact_evidence: No release artifact is published; report schema validation is covered by local and client evidence categories.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-MATRIX-CELL-TIMEOUT-KILL | VPD-1787497252661429 | Timeout test asserts no surviving child after cancellation | Pending |
| REQ-MATRIX-CONTROL-TIMEOUT | VPD-1787497252679177 | Unit test with hanging control stub records Unknown and continues | Pending |
| REQ-MATRIX-DURABILITY | VPD-1787497252698055 | Interrupt simulation leaves partial marked report with nonzero exit; duration 0 rejected | Pending |
| REQ-MATRIX-EVIDENCE-SEMANTICS | VPD-1787497252715025 | windows() unit tests: Unknown-only series yields none; refreshed snapshot reviewed | Pending |
