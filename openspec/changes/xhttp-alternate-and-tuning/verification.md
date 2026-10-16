---
task_id: "XRY-1791617991738391"
change: "xhttp-alternate-and-tuning"
commit_sha: null
local: "required"
local_evidence: "complete affected suites plus the named native positive/failure cases after implementation"
remote_ci: "not_applicable"
remote_ci_evidence: "Owner selected local completion on 2026-10-16; complete local source gates are required. Automatic PR checks remain separate review evidence."
dry_run: "not_applicable"
dry_run_evidence: "source capability is exercised in isolated local/native runtime; no real inventory run is part of this task"
staging: "not_applicable"
staging_evidence: "Owner removed staging soak on 2026-10-16; isolated local runtime acceptance is required instead."
live: "not_applicable"
live_evidence: "no production rollout is part of this source or disabled-default feature task"
client: "not_applicable"
client_evidence: "Owner removed external and device acceptance on 2026-10-16; real local protocol engines remain required under local evidence."
artifact: "required"
artifact_evidence: "rendered contracts and redacted requirement-specific exact-source artifacts after implementation"
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


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
