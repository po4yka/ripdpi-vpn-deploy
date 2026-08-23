---
task_id: VPD-1787497426503364
change: vpd-1787497426503364-vpnd-operator-output-contract
commit_sha: null
local: required
local_evidence: ""
remote_ci: required
remote_ci_evidence: ""
dry_run: not_applicable
dry_run_evidence: no Terraform surface
staging: not_applicable
staging_evidence: covered by local tests and CI cargo suite
live: not_applicable
live_evidence: no deployed-state dependency
client: not_applicable
client_evidence: client-facing emitters unaffected
artifact: not_applicable
artifact_evidence: man page is build output, no artifact contracts
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-MANPAGE-SYNC | VPD-1787497435906087 | Parity gate test fails on seeded drift between cli.rs and generated man page | Pending |
| REQ-JSON-FLAG-HONESTY | VPD-1787497435909140 | Tests assert per-subcommand JSON emission or flag absence per the decision | Pending |
| REQ-CLIP-REQUIRES-AI | VPD-1787497435912334 | Test asserts parse-time error for --clip without --ai | Pending |
| REQ-DOCTOR-RESILIENCE | VPD-1787497435914528 | doctor_bundle tests assert stderr capture, continued execution, failed-step marks, nonzero exit | Pending |
