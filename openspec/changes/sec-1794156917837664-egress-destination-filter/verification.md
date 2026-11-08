---
task_id: SEC-1794156917837664
change: sec-1794156917837664-egress-destination-filter
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EDF-DEFAULT-OFF | SEC-1794158806186281 | Pending: snapshot and Molecule run with the toggle disabled | Not run |
| REQ-EDF-ENFORCE | SEC-1794158301568776 | Pending: unit tests for name and range denial | Not run |
| REQ-EDF-ENFORCE | SEC-1794160777177995 | Pending: staging denial on P0, P1 and Hysteria2 | Not run |
| REQ-EDF-ALLOW | SEC-1794158301568776 | Pending: unit tests for allow list and address isolation | Not run |
| REQ-EDF-INPUT | SEC-1794158806186281 | Pending: Molecule run with a digest mismatch and invalid data | Not run |
| REQ-EDF-CONTROL-PATHS | SEC-1794159684079419 | Pending: unit test that refuses data that denies the canary or REALITY target | Not run |
| REQ-EDF-PRIVACY | SEC-1794158301568776 | Pending: unit test of denial output and logs | Not run |
| REQ-EDF-BOUNDS | SEC-1794157748624712 | Pending: memory measurement on the smallest node class | Not run |
| REQ-EDF-COVERAGE | SEC-1794160231676642 | Pending: `make docs-check` and review of the coverage section | Not run |
