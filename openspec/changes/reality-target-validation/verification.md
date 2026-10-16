---
task_id: "SCR-1791617975137354"
change: "reality-target-validation"
commit_sha: "4e043c0f72345d3e3767415a56fead2391466913"
local: "passed"
local_evidence: "Exact source 4e043c0f: complete affected portable suites (validator, monitor, scanner, self-steal and executable coverage), 88 passed; isolated Linux make test-reality-target-validation, 72 passed, zero skips. make validate, task-check, shellcheck, actionlint, zizmor and commit hooks passed. Full Mac make check exposed pre-existing sing-box 1.13.16 versus required 1.14.3; the clean main reproduces it. A session-only checksum-verified 1.14.3 parser passes liveness compatibility. A full gated retry then hit registry.terraform.io timeouts; a session-only filesystem mirror of the existing locked provider packages passes init without registry access. The next full gated run waits for the shared build slot and is not claimed passed."
remote_ci: "passed"
remote_ci_evidence: "Native workflow 38895410063 passed all 72 cases and published exact-source artifacts. Full CI https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38895409950 completed success on exact source 4e043c0f72345d3e3767415a56fead2391466913 (all 88 jobs). CodeQL 38895409909, markdown-link-check 38895409927, claude-md-touch 38895409923 and native REALITY workflow 38895410063 also completed success."
dry_run: "not_applicable"
dry_run_evidence: "source capability is exercised in isolated local/native runtime; no real inventory run is part of this task"
staging: "not_applicable"
staging_evidence: "source-only scope; isolated native behavior is required, and any external rollout is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout is part of this source or disabled-default feature task"
client: "passed"
client_evidence: "Exact checksum-pinned curl-impersonate 0.6.1 Chrome116 completed real TLS 1.3/H2 traffic. H2 downgrade fails separately from passing hygiene; unavailable OS execution remains unavailable; ambient curlrc is ignored. Native workflow https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/38895410063 passed all 72 cases without skips."
artifact: "passed"
artifact_evidence: "Downloaded and inspected GitHub artifact 12043906727 from workflow 38895410063: ten redacted JSON observations bind source 4e043c0f72345d3e3767415a56fead2391466913 and tested merge 6d5b2191dbbff2bcbf676299979a5b3b0524e04c; JUnit proves 72 tests with zero failures/errors/skips. Actual pinned-client success, unavailable execution and owned-public ingress observations are present."
---

# Verification

## Requirement evidence

The controlled positive and failure cases below were observed on the exact source above. The complete exact-source hosted CI gate passed; local hygiene and native client evidence do not establish filtered-path or production acceptance. Full local make check was attempted but remains unavailable due the documented toolchain/network/resource constraints; no local full-gate success is claimed.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RTV-IDENTITY | SCR-1791617985610703 | test_validate_reality_target.py with controlled exact wildcard deep-label mixed comma/space duplicate and empty-name cases. | passed |
| REQ-PROTO-RTV-IDENTITY | SCR-1791617989032738 | test_validate_reality_target.py with controlled exact wildcard deep-label mixed comma/space duplicate and empty-name cases. | passed |
| REQ-PROTO-RTV-DEADLINES | SCR-1791617986915903 | Real subprocess deadline and child-cleanup tests for DNS TLS HTTP and multi-name aggregate work; retain current monitor state tests. | passed |
| REQ-PROTO-RTV-DEADLINES | SCR-1791617989032738 | Real subprocess deadline and child-cleanup tests for DNS TLS HTTP and multi-name aggregate work; retain current monitor state tests. | passed |
| REQ-PROTO-RTV-CLAIMS | SCR-1791617987865403 | Real pinned-client and truthful-report tests; inspect real handshake execution boundary rather than using a User-Agent assertion as proof. | passed |
| REQ-PROTO-RTV-CLAIMS | SCR-1791617989032738 | Real pinned-client and truthful-report tests; inspect real handshake execution boundary rather than using a User-Agent assertion as proof. | passed |
| REQ-PROTO-RTV-OWNERSHIP | SCR-1791617986915903 | Real owned service ingress, public-path/loopback distinction and no-mutation/privacy regressions, reusing current self-steal transaction fixtures for accepted authority preservation. | passed |
| REQ-PROTO-RTV-OWNERSHIP | SCR-1791617987865403 | Real owned service ingress, public-path/loopback distinction and no-mutation/privacy regressions, reusing current self-steal transaction fixtures for accepted authority preservation. | passed |
| REQ-PROTO-RTV-OWNERSHIP | SCR-1791617989032738 | Real owned service ingress, public-path/loopback distinction and no-mutation/privacy regressions, reusing current self-steal transaction fixtures for accepted authority preservation. | passed |


## Observed source evidence

- Identity: real trusted exact/SAN and single-label wildcard handshakes; malformed names, IP-literal SNI, deep wildcards, Common Name without SAN, expired/untrusted certificates and missing H2 refuse.
- Deadlines: real stalled DNS/TLS/HTTP/metadata command trees, an actual stalled TLS socket, multi-name aggregate exhaustion, output flooding and cancellation reclaim owned descendants. Successful commands also remove leftover children.
- Claims: ordinary curl is hygiene; the exact supported Chrome116 engine performs actual H2. Missing or changed client bytes remain unavailable; H2 downgrade is a separate failed client observation.
- Ownership/privacy: an explicit ingress and owned SNI bind self-steal; loopback and mismatched SNI refuse. Private source bytes survive failed validation. Existing self-steal role regressions passed 15/15; full CI native transport transaction acceptance also passed.
- Promotion authority: target/certificate mutation, real deployment, supported VPN recipient authentication and approved filtered-vantage survival are outside this source-only task. Runtime pins and PQE HOLD remain unchanged.

Security review: APPROVE. Exact client checksums, redacted categorical diagnostics, retained owned process cleanup and no credential/deployment mutation were reviewed; make validate and normal commit hooks passed. The final test-only cleanup removes an unsafe fallback signal to a potentially reused PID without changing the failure assertion; its complete file passed 36/36.
