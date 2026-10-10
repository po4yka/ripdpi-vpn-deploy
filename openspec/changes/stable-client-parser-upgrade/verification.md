---
task_id: "TST-1791618376497512"
change: "stable-client-parser-upgrade"
commit_sha: null
local: "required"
local_evidence: "complete affected tests, exact native cases and full source gates after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal required checks on the exact integrated implementation SHA"
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "isolated native source acceptance owns this change; fleet rehearsal requires separate authorization"
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "required"
client_evidence: "real isolated consuming-client behavior named in the requirements; not host activity alone"
artifact: "required"
artifact_evidence: "validated contracts, private redacted outputs and requirement-to-test evidence on the exact implementation SHA"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-PARSER-INTEGRITY | TST-1791618385464569 | Installer transaction and checksum failure tests with verified real candidate version output. | required |
| REQ-PROTO-PARSER-PAYLOADS | TST-1791618386942234 | Complete emit_singbox_roundtrip and liveness suites plus native-four-protocol acceptance on old/candidate inputs. | required |
| REQ-PROTO-PARSER-ROLLBACK | TST-1791618388220484 | Actual installed-tool rollback and complete hosted parser/native jobs with exact-SHA evidence. | required |
| REQ-PROTO-PARSER-ELIGIBILITY | TST-1791618385464569 | Deterministic release-age boundaries, unknown metadata and advisory cases; actual candidate parser/native compatibility remains a separate mandatory gate. | required |
