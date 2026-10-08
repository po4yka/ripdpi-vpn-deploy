---
task_id: TFR-1791469128152528
change: tfr-1791469128152528-select-the-actual-vultr-debian-13-image-for-disposable-nodes
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Terraform plan and mock-provider cases are the image-selection gate; runtime dry-run belongs to fleet acceptance.
staging: not_applicable
staging_evidence: The already authorized permanent disposable replacement provides actual image evidence.
live: required
live_evidence: null
client: not_applicable
client_evidence: This image-selection change claims no authenticated protocol or client delivery acceptance.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-VULTR-DEBIAN13-ID | TFR-1791469302312711 | Mock-provider plans and rejected unsupported images; coherent examples | Required |
| REQ-VULTR-IMAGE-CHANGE-ISOLATION | TFR-1791469302916838 | Exact-source CI, reviewed new-node plan, actual OS and strict SSH foundation | Required |
