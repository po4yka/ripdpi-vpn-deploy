---
task_id: SEC-1794728606515594
change: sec-1794728606515594-node-address-disclosure
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The watchdog change reaches the existing nodes through the ordinary deploy transaction; the script changes run on the operator workstation.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-NAD-PRIVATE-ALERTS | SEC-1794728786307882 | Watchdog snapshot and Molecule cases; argument-list test for the notification call sites | required |
| REQ-SEC-NAD-BURN-CHECK-LOCAL | SEC-1794728798422428 | Burn-check tests with a stub `curl`; rendered crontab test | required |
| REQ-SEC-NAD-ENCRYPTED-LOOKUPS | SEC-1794728810946200 | Reputation and ASN script tests with stub resolvers, including the fail-closed case | required |
| REQ-SEC-NAD-PRIVATE-REPORTS | SEC-1794728832615527 | Probing-summary test for path, mode and file name | required |
| REQ-SEC-NAD-TRACKED-ADDRESS-GUARD | SEC-1794728832615527 | Identifier policy test with accept and reject cases | required |
