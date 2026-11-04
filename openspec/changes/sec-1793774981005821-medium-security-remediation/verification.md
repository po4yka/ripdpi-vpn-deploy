---
task_id: SEC-1793774981005821
change: sec-1793774981005821-medium-security-remediation
commit_sha: 25228e6a
local: passed
local_evidence: "Backup grant tests 11 passed; public-site version test fails without the fix and passes with it; terraform management tests passed in hetzner (25), scaleway (17), upcloud (27) and vultr (17); collector unit tests 387 passed, make snapshot-check 173 templates matched, make validate passed. Molecule did not run: the pinned image needs registry credentials."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request.
dry_run: required
dry_run_evidence: Pending dry-run of node-a, node-b and node-c.
staging: not_applicable
staging_evidence: The change is rolled out to the existing production nodes through the ordinary deploy transaction.
live: required
live_evidence: Pending deploy, verify and external probes.
client: required
client_evidence: Pending authenticated REALITY round trip through the regenerated P0 probe profile.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-OSH-BACKUP-APPEND-ONLY | SEC-1793776165979531 | Unit refusals; live check accepts the reissued keys and refuses the previous keys with `append-only-grant-required` | required |
| REQ-SEC-OSH-INGEST-NODE-LABEL | SEC-1793776927682536 | Render tests only; Molecule and live forged-label proof pending | required |
| REQ-SEC-OSH-SSH-PREFIX-FLOOR | SEC-1793777693877736 | Terraform tests in four roots | passed |
| REQ-SEC-OSH-HTTP-VERSION-HIDDEN | SEC-1793778451096956 | Render test; live probe pending | required |
| REQ-SEC-OSH-REALITY-SAME-HOST | SEC-1793778849874329 | DNS record and certificate issued; deploy pending | required |
