---
task_id: "SCR-1791618039091425"
change: "awg-device-binding"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "required"
client_evidence: "actual supported recipient parser and real authenticated protocol behavior"
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-BIND | SCR-1791618044456243 | Extend test_emit_bundle_host_selection and add canonical binding tests comparing real role renders, standalone emitter, RIPDPI bundle and liveness resolver; inspect only synthetic public summaries. | required |
| REQ-PROTO-AWG-BIND | SCR-1791618045793096 | Extend test_emit_bundle_host_selection and add canonical binding tests comparing real role renders, standalone emitter, RIPDPI bundle and liveness resolver; inspect only synthetic public summaries. | required |
| REQ-PROTO-AWG-BIND | SCR-1791618046582572 | Extend test_emit_bundle_host_selection and add canonical binding tests comparing real role renders, standalone emitter, RIPDPI bundle and liveness resolver; inspect only synthetic public summaries. | required |
| REQ-PROTO-AWG-ENROLL | SCR-1791618045140064 | Exercise real SOPS/age temporary encrypted documents and actual enrollment/revocation scripts, including distinct public keys, pool limits, lock behavior and interrupted publication; fixtures are not live delivery proof. | required |
| REQ-PROTO-AWG-ENROLL | SCR-1791618046582572 | Exercise real SOPS/age temporary encrypted documents and actual enrollment/revocation scripts, including distinct public keys, pool limits, lock behavior and interrupted publication; fixtures are not live delivery proof. | required |
| REQ-PROTO-AWG-PARITY | SCR-1791618044456243 | Add shared semantic boundary tests, fingerprint golden cases and an exact-binary Linux TUN positive/negative fixture; retain arm64 floor tests. | required |
| REQ-PROTO-AWG-PARITY | SCR-1791618045793096 | Add shared semantic boundary tests, fingerprint golden cases and an exact-binary Linux TUN positive/negative fixture; retain arm64 floor tests. | required |
| REQ-PROTO-AWG-PARITY | SCR-1791618046582572 | Add shared semantic boundary tests, fingerprint golden cases and an exact-binary Linux TUN positive/negative fixture; retain arm64 floor tests. | required |
| REQ-PROTO-AWG-PRIVATE | SCR-1791618044456243 | Run verbose-callback secret-leak regressions, unsafe output-path tests, migration fixtures and an all-caller discovery assertion; use synthetic secret markers only. | required |
| REQ-PROTO-AWG-PRIVATE | SCR-1791618045140064 | Run verbose-callback secret-leak regressions, unsafe output-path tests, migration fixtures and an all-caller discovery assertion; use synthetic secret markers only. | required |
| REQ-PROTO-AWG-PRIVATE | SCR-1791618046582572 | Run verbose-callback secret-leak regressions, unsafe output-path tests, migration fixtures and an all-caller discovery assertion; use synthetic secret markers only. | required |
