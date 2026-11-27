---
task_id: SCR-1795774108061951
change: scr-1795774108061951-management-route-warmup
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The change touches only the operator-side deploy controller; no staging node behaviour changes.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client contract or payload changes.
artifact: not_applicable
artifact_evidence: No build or release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-ROUTE-WARMUP | SCR-1795774279138177 | Controller unit tests for the warm-up probe and the unreachable refusal | Pending |
| REQ-OPS-ROUTE-SCOPE | SCR-1795774279138177 | Controller unit tests for the CI handoff, public and host-name transports | Pending |
| REQ-OPS-ROUTE-BOTH-MODES | SCR-1795774279138177 | Controller unit tests for the dry-run gate; live preview route report | Pending |
| REQ-OPS-ROUTE-SILENCE | SCR-1795774324586353 | Controller unit tests for the shared master options and absent retries | Pending |
