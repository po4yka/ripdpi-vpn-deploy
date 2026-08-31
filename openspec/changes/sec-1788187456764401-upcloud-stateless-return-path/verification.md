---
task_id: SEC-1788187456764401
change: sec-1788187456764401-upcloud-stateless-return-path
commit_sha: "96242a81960ebe4c943856e86dc6086d42620350"
local: passed
local_evidence: "Exact main ae0af37 source full: Python 2617 PASS + 1 existing skip, BATS 55, Terraform 97, Conftest 45, Rust and Clippy, ci-fast OK; guarded-destroy follow-up 96242a8: 148 focused unit tests and configured hooks PASS."
remote_ci: required
remote_ci_evidence: "Exact main ae0af37 CI 33413847757 SUCCESS 51/51, CodeQL 33413847458 SUCCESS, Scorecard 33413847276 SUCCESS; exact CI for the portable guarded-destroy follow-up is pending."
dry_run: passed
dry_run_evidence: "Saved isolated plans showed only the canonical three-resource create, then a single server firewall false-to-true update with no create/delete/replace, then 0 add / 0 change / 3 destroy for the exact owned resources."
staging: passed
staging_evidence: "One isolated UpCloud node passed first-boot readiness, recovery foundation, guest stateful firewall, strict SSH, five required IPv4 public listeners before and after provider-firewall activation, outbound IPv4 DNS/TLS, and host-side outbound IPv6 TCP/UDP. Guarded destruction completed within the fixed deadline; private provider evidence reports server and root storage absent, an independent API check matched the bound account and returned 404 for both resources, the hostname list count is zero, and Terraform state has zero managed instances. Production was unchanged."
live: not_applicable
live_evidence: Production adoption is outside this isolated staging correction.
client: not_applicable
client_evidence: No client contract changes.
artifact: passed
artifact_evidence: "Private mode-0600 evidence index SHA256 35298ad3f5c711994a50f958f0d1e6ddef80097c91e95f1bcd81a5f70fce272c covers 13 staged activation and cleanup artifacts; no credentials, state, UUIDs, addresses, or raw plans are committed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-UPF-ACTIVATION | SEC-1788187699228713 | Exact source tests and isolated false-to-true activation plan/apply | passed |
| REQ-UPF-RETURN | SEC-1788187699228713 | Required listeners plus outbound IPv4 and IPv6 TCP/UDP passed after activation | passed |
| REQ-UPF-BOUNDARY | SEC-1788187712724429 | Strict SSH and unchanged terminal deny exposure passed before and after activation | passed |
| REQ-UPF-STAGING | SEC-1788187714043182 | Isolated acceptance, exact guarded destroy, provider absence, and empty state verified | passed |
