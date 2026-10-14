---
task_id: "XRY-1791617955392712"
change: "xhttp-endpoint-contract"
commit_sha: "7a08fcd7052351ef968988c2b79a0c57a33060aa"
local: "passed"
local_evidence: "make check passed: 6823 portable cases, 22 subtests, 59 shell cases and 303 CLI cases; 73 supplemental endpoint/runtime-fixture regressions cover the final fixture changes"
remote_ci: "passed"
remote_ci_evidence: "CI run 38557712653 and CodeQL run 38557712652 succeeded on 7a08fcd7052351ef968988c2b79a0c57a33060aa: 93 successful checks and optional Trivy neutral; 138 baseline native, two endpoint native and four runtime acceptance cases passed"
dry_run: "not_applicable"
dry_run_evidence: "source capability is exercised in isolated local/native runtime; no real inventory run is part of this task"
staging: "not_applicable"
staging_evidence: "source-only scope; isolated native behavior is required, and any external rollout is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout is part of this source or disabled-default feature task"
client: "passed"
client_evidence: "exact pinned Xray clients from canonical emission and liveness conversion completed real isolated TLS/payload probes at primary ports 443/8443 and alternate 2083; local ARM64 and hosted AMD64 endpoint cases passed"
artifact: "passed"
artifact_evidence: "163 reviewed snapshots match; emitted selected-device identity, canonical discovery/origin outputs, categorical preflight refusal and private native attribution observations passed on the recorded source"
---

# Verification

## Requirement evidence

The recorded implementation source passed the complete local gate, independent standards/security and spec reviews, and terminal exact-source hosted checks. This is source and isolated native/client acceptance; no production or private-input migration is claimed.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-XEC-PATH | XRY-1791617961367849 | test_xhttp_endpoint_contract.py admission/schema boundaries; canonical emitter and liveness output complete pinned native XHTTP payload transfer. | passed |
| REQ-PROTO-XEC-PATH | XRY-1791617963780756 | test_xhttp_endpoint_contract.py admission/schema boundaries; canonical emitter and liveness output complete pinned native XHTTP payload transfer. | passed |
| REQ-PROTO-XEC-PATH | XRY-1791617971846326 | test_xhttp_endpoint_contract.py admission/schema boundaries; canonical emitter and liveness output complete pinned native XHTTP payload transfer. | passed |
| REQ-PROTO-XEC-ATTRIBUTION | XRY-1791617962188506 | test_xhttp_endpoint_contract_native.py observes the actual private backend peer at both primary ports and alternate 2083, with absent and forged forwarding headers. | passed |
| REQ-PROTO-XEC-ATTRIBUTION | XRY-1791617971846326 | test_xhttp_endpoint_contract_native.py observes the actual private backend peer at both primary ports and alternate 2083, with absent and forged forwarding headers. | passed |
| REQ-PROTO-XEC-ORIGIN | XRY-1791617961367849 | Shared extra-vars and transport admission, public_site_contract tests, native HTTPS metadata/feed/sitemap/robots/redirects and verified Hysteria masquerade agree with the served origin. | passed |
| REQ-PROTO-XEC-ORIGIN | XRY-1791617963780756 | Shared extra-vars and transport admission, public_site_contract tests, native HTTPS metadata/feed/sitemap/robots/redirects and verified Hysteria masquerade agree with the served origin. | passed |
| REQ-PROTO-XEC-ORIGIN | XRY-1791617971846326 | Shared extra-vars and transport admission, public_site_contract tests, native HTTPS metadata/feed/sitemap/robots/redirects and verified Hysteria masquerade agree with the served origin. | passed |
| REQ-PROTO-XEC-PRESERVATION | XRY-1791617962188506 | Complete native Nginx candidate refusal retains accepted files and traffic; inherited activation/interruption coverage, selected-device emission, unsupported-client refusal and ordinary-log privacy pass. | passed |
| REQ-PROTO-XEC-PRESERVATION | XRY-1791617963780756 | Complete native Nginx candidate refusal retains accepted files and traffic; inherited activation/interruption coverage, selected-device emission, unsupported-client refusal and ordinary-log privacy pass. | passed |
| REQ-PROTO-XEC-PRESERVATION | XRY-1791617971846326 | Complete native Nginx candidate refusal retains accepted files and traffic; inherited activation/interruption coverage, selected-device emission, unsupported-client refusal and ordinary-log privacy pass. | passed |

## Observed source and native checks

- The pre-change endpoint regression module reported 44 failures and eight passes, reproducing path/origin/header defects.
- The complete affected portable suite passed 478 cases with 14 native cases deliberately partitioned into native execution. Later hostname-only metadata and standard-client refusal checks are included in final validation.
- Actual localhost Nginx admission in normal/check mode preserves the pre-mutation marker on invalid paths and origin disagreement; the focused preflight/fixture modules passed 91 cases. All nine bootstrap shell cases passed.
- `make test-xhttp-endpoint-contract` passed both complete native cases in 149.13 seconds on Linux ARM64 with repository-pinned Xray/Hysteria bytes. The canonical exporter and liveness transformation produced the actual positive client. Synthetic Terraform metadata supplied only the disconnected endpoint input; this is no provider acceptance. Primary and alternate requests retained actual peer attribution under forged headers, HTTPS discovery matched the served origin, native candidate refusal retained prior files/traffic, Hysteria reached the verified origin, and ordinary logs plus global hosts preserved their boundaries.
- The complete inherited `test_nginx_transaction_native.py` passed in 52.55 seconds, retaining native TLS, activation compensation and interruption cases.
- `make snapshot-check` passed all 163 templates after reviewed port/header/hostname metadata updates. OpenSpec strict validation, task contracts and shellcheck passed.
- The full `make check` gate passed: 6,823 portable tests and 22 subtests, all 59 shell cases, all 303 CLI cases, and the complete transfer/parity checks. The final fixture correction also passed the complete 73-case endpoint/runtime-fixture regression set. All six literal Make input cases and both full-stack origin admission cases passed; no test or validator was weakened.
- Independent standards/security and spec reviews approved the final implementation and fixture corrections with no remaining actionable findings.
- Hosted CI run 38557712653 and CodeQL run 38557712652 passed on `7a08fcd7052351ef968988c2b79a0c57a33060aa`. All 93 successful contexts were terminal; the separate optional Trivy check was neutral. Native integration passed 138 baseline cases in 1,006.53 seconds, followed by both endpoint cases in 151.93 seconds. The complete four-case runtime acceptance lane passed in 1,883.74 seconds, including canonical Xray/Hysteria upgrades, unchanged retries, combined retirement and validation-lease interruption recovery.
- Older test fixtures intentionally refused the new input contract until their origins included the actual port or removed the trailing path separator. Their native assertions remain intact. The task-owned local native container was removed after acceptance; no real inventory, private operator input or deployment is included.
