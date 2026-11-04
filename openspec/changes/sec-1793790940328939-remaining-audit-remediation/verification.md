---
task_id: SEC-1793790940328939
change: sec-1793790940328939-remaining-audit-remediation
commit_sha: b68a21d7
local: passed
local_evidence: "Vultr DNS tftest 17 passed; transport sandbox test 10 passed and fails without the Xray change; recipient policy and firewall tests 272 passed (native namespace tests fail identically on the unchanged base); control-plane alerting with promtool 3.15.1 62 passed; adapter, operator-automation and audit-regression tests 157 passed; make snapshot-check 174 templates matched. Molecule did not run."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request.
dry_run: required
dry_run_evidence: Pending dry-run of the affected nodes after merge.
staging: not_applicable
staging_evidence: The change is rolled out to the existing production nodes through the ordinary deploy transaction.
live: required
live_evidence: Pending deploy, the DNS record plan and external probes.
client: not_applicable
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-RSH-DNS-POLICY-RECORDS | SEC-1793791408648983 | Vultr DNS tftest accept and reject cases | passed |
| REQ-SEC-RSH-EMBEDDED-IPV4-DENY | SEC-1793791827276913 | Recipient policy cases and nftables/gateway snapshots | passed |
| REQ-SEC-RSH-XRAY-SANDBOX | SEC-1793792244192848 | Transport sandbox test; live start pending | required |
| REQ-SEC-RSH-SELF-STEAL-EXPIRY | SEC-1793792655608435 | Promtool expiry cases and adapter tests; live series pending | required |
| REQ-SEC-RSH-RELAY-DROPS | SEC-1793792655608435 | Promtool relay drop cases; live scrape pending | required |
