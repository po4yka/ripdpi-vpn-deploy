---
task_id: "XRY-1791617955392712"
change: "xhttp-endpoint-contract"
commit_sha: null
local: "required"
local_evidence: "complete affected suites plus the named native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability is exercised in isolated local/native runtime; no real inventory run is part of this task"
staging: "not_applicable"
staging_evidence: "source-only scope; isolated native behavior is required, and any external rollout is separately authorized"
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
| REQ-PROTO-XEC-PATH | XRY-1791617961367849 | NEW test_xhttp_endpoint_contract.py plus existing schema relay and liveness profile tests; include native request completion and parameterized rejected path shapes. | required |
| REQ-PROTO-XEC-PATH | XRY-1791617963780756 | NEW test_xhttp_endpoint_contract.py plus existing schema relay and liveness profile tests; include native request completion and parameterized rejected path shapes. | required |
| REQ-PROTO-XEC-PATH | XRY-1791617971846326 | NEW test_xhttp_endpoint_contract.py plus existing schema relay and liveness profile tests; include native request completion and parameterized rejected path shapes. | required |
| REQ-PROTO-XEC-ATTRIBUTION | XRY-1791617962188506 | NEW native nginx-to-pinned-Xray attribution tests for primary alternate no-header and conflicting-header cases; assert privacy-safe technical source observations. | required |
| REQ-PROTO-XEC-ATTRIBUTION | XRY-1791617971846326 | NEW native nginx-to-pinned-Xray attribution tests for primary alternate no-header and conflicting-header cases; assert privacy-safe technical source observations. | required |
| REQ-PROTO-XEC-ORIGIN | XRY-1791617961367849 | Extend test_validate_ansible_extra_vars.py and test_public_site_contract.py with port-aware native HTTPS discovery and masquerade checks. | required |
| REQ-PROTO-XEC-ORIGIN | XRY-1791617963780756 | Extend test_validate_ansible_extra_vars.py and test_public_site_contract.py with port-aware native HTTPS discovery and masquerade checks. | required |
| REQ-PROTO-XEC-ORIGIN | XRY-1791617971846326 | Extend test_validate_ansible_extra_vars.py and test_public_site_contract.py with port-aware native HTTPS discovery and masquerade checks. | required |
| REQ-PROTO-XEC-PRESERVATION | XRY-1791617962188506 | Reuse existing nginx transaction and private output regressions; extend endpoint native tests and supported versus official client parser boundaries. | required |
| REQ-PROTO-XEC-PRESERVATION | XRY-1791617963780756 | Reuse existing nginx transaction and private output regressions; extend endpoint native tests and supported versus official client parser boundaries. | required |
| REQ-PROTO-XEC-PRESERVATION | XRY-1791617971846326 | Reuse existing nginx transaction and private output regressions; extend endpoint native tests and supported versus official client parser boundaries. | required |
