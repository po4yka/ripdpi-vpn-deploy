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

The source/native checks below were observed in the isolated implementation worktree. Final full-gate, independent review and exact-source CI evidence remain required before portfolio review.

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

## Observed source and native checks

- The pre-change endpoint regression module reported 44 failures and eight passes, reproducing path/origin/header defects.
- The complete affected portable suite passed 478 cases with 14 native cases deliberately partitioned into native execution. Later hostname-only metadata and standard-client refusal checks are included in final validation.
- Actual localhost Nginx admission in normal/check mode preserves the pre-mutation marker on invalid paths and origin disagreement; the focused preflight/fixture modules passed 91 cases. All nine bootstrap shell cases passed.
- `make test-xhttp-endpoint-contract` passed both complete native cases in 149.13 seconds on Linux ARM64 with repository-pinned Xray/Hysteria bytes. The canonical exporter and liveness transformation produced the actual positive client. Synthetic Terraform metadata supplied only the disconnected endpoint input; this is no provider acceptance. Primary and alternate requests retained actual peer attribution under forged headers, HTTPS discovery matched the served origin, native candidate refusal retained prior files/traffic, Hysteria reached the verified origin, and ordinary logs plus global hosts preserved their boundaries.
- The complete inherited `test_nginx_transaction_native.py` passed in 52.55 seconds, retaining native TLS, activation compensation and interruption cases.
- `make snapshot-check` passed all 163 templates after reviewed port/header/hostname metadata updates. OpenSpec strict validation, task contracts and shellcheck passed.
- `make check`, independent review and terminal exact-SHA hosted checks are in progress; no source or task completion is inferred from these pending gates. No real inventory, private operator input or deployment is included.
