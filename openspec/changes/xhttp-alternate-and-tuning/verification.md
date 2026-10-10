---
task_id: "XRY-1791617991738391"
change: "xhttp-alternate-and-tuning"
commit_sha: null
local: "required"
local_evidence: "complete affected suites plus the named native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability is exercised in isolated local/native runtime; no real inventory run is part of this task"
staging: "required"
staging_evidence: "separately authorized exact-target comparative traffic and rollback before optional feature promotion"
live: "not_applicable"
live_evidence: "no production rollout is part of this source or disabled-default feature task"
client: "required"
client_evidence: "exact supported real client completes the named isolated protocol or TLS probe cases"
artifact: "required"
artifact_evidence: "rendered contracts and redacted requirement-specific exact-source artifacts after implementation"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-XAT-ALTERNATE | XRY-1791618003859679 | NEW test_xhttp_alternate_profiles.py plus exact client delivery matrix with distinct host/port, certificate mismatch, disabled listener and official unsupported-client cases. | required |
| REQ-PROTO-XAT-ALTERNATE | XRY-1791618006858260 | NEW test_xhttp_alternate_profiles.py plus exact client delivery matrix with distinct host/port, certificate mismatch, disabled listener and official unsupported-client cases. | required |
| REQ-PROTO-XAT-ALTERNATE | XRY-1791618008836301 | NEW test_xhttp_alternate_profiles.py plus exact client delivery matrix with distinct host/port, certificate mismatch, disabled listener and official unsupported-client cases. | required |
| REQ-PROTO-XAT-TYPED | XRY-1791618006858260 | NEW schema and exact native profile matrix tests for each approved mode and bound, including explicit unsupported field/version rejection. | required |
| REQ-PROTO-XAT-TYPED | XRY-1791618008836301 | NEW schema and exact native profile matrix tests for each approved mode and bound, including explicit unsupported field/version rejection. | required |
| REQ-PROTO-XAT-MEASURED | XRY-1791618007864586 | NEW credential-free xhttp_delivery_matrix using exact clients and deterministic controlled faults; preserve raw technical measurements and declared acceptance thresholds. | required |
| REQ-PROTO-XAT-MEASURED | XRY-1791618008836301 | NEW credential-free xhttp_delivery_matrix using exact clients and deterministic controlled faults; preserve raw technical measurements and declared acceptance thresholds. | required |
| REQ-PROTO-XAT-ROLLBACK | XRY-1791618003859679 | Reuse destination boundary and runtime acceptance native suites; add private artifact, bearer-log and unchanged PQE HOLD/classical-P0 guard regressions to the feature matrix. | required |
| REQ-PROTO-XAT-ROLLBACK | XRY-1791618007864586 | Reuse destination boundary and runtime acceptance native suites; add private artifact, bearer-log and unchanged PQE HOLD/classical-P0 guard regressions to the feature matrix. | required |
| REQ-PROTO-XAT-ROLLBACK | XRY-1791618008836301 | Reuse destination boundary and runtime acceptance native suites; add private artifact, bearer-log and unchanged PQE HOLD/classical-P0 guard regressions to the feature matrix. | required |
