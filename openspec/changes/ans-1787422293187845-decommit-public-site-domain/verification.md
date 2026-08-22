---
task_id: ANS-1787422293187845
change: ans-1787422293187845-decommit-public-site-domain
commit_sha: null
local: passed
local_evidence: pytest tests/unit/test_public_site_contract.py (27 passed), tests/unit/test_validate_ansible_extra_vars.py (20 passed), full pytest tests/unit green with refreshed governance count, make validate green
remote_ci: blocked
remote_ci_evidence: pending required checks on the remediation PR; record SHA and run on merge
dry_run: not_applicable
dry_run_evidence: no deploy executed; convergence behavior is covered by role asserts and unit contracts
staging: not_applicable
staging_evidence: placeholder matches the hysteria masquerade default, so lab profiles converge unchanged by construction
live: blocked
live_evidence: next production deploy on the p1-web/p2-udp profiles must pass the decoy origin via ANSIBLE_EXTRA_VARS_FILE; operator to record the run after merge
client: not_applicable
client_evidence: no client-facing emitter changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SITE-OVERRIDE | ANS-1787422768124258 | `rg chinallmodel` over the working tree returns only the contract-test negative assertion; both profiles carry `https://vpn.example.com` | Passed |
| REQ-SITE-OVERRIDE | ANS-1787422768125988 | `test_accepts_https_origin_decoy_overrides` and `test_rejects_malformed_decoy_overrides` (http scheme, bare host, trailing path, page path, space in host, non-string) pass | Passed |
| REQ-SITE-OVERRIDE | ANS-1787422768126654 | `test_committed_profiles_carry_only_the_neutral_placeholder_origin` pins every group_vars file declaring the key | Passed |
| REQ-SITE-OVERRIDE-HISTORY | ANS-1787422768127223 | docs/DEPLOY-PROFILES.md "Decoy site identity" section documents rotation via untracked 0600 override + secrets, no committed edits | Passed |
| Fail-closed backstop | ANS-1787422768124258 | nginx-xhttp assert (`public_site_canonical_url == https://<server_name>`) and hysteria assert (`masquerade_url == public_site_canonical_url`) unchanged; a forgotten override fails before listener changes | Passed |

## Notes

- History retains the old domain association; it is treated as already burned.
  This change guarantees the *next* identity never enters version control.
- The governance test count in docs/TESTING.md is refreshed in the same
  commit sequence because live collection changes with the new tests.
