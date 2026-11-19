---
task_id: SEC-1795086333272606
change: sec-1795086333272606-field-report-ingest-d2
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Enabling on production is a separate operator decision.
client: not_applicable
client_evidence: Client traffic is proven by D7 with RIPDPI R3.
artifact: not_applicable
artifact_evidence: No release artifact is produced by this change.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-INGEST-VALIDATE | SEC-1795086432958533 | unit tests for 400, 401, 413, 429 and valid acceptance | planned |
| REQ-INGEST-NOIP | SEC-1795086432958533 | unit test searching logs, metrics and state for the test address and token | planned |
| REQ-INGEST-LABELS | SEC-1795086432958533 | unit test with 1000 ASNs bounds series count | planned |
| REQ-INGEST-MINATTEMPT | SEC-1795086432958533 | unit test with 4 and 5 attempts buckets | planned |
| REQ-INGEST-ALERT | SEC-1795086408877793 | promtool test case in observability-alert-rules.test.yml.j2 | planned |
| REQ-INGEST-SECREVIEW | SEC-1795086456490841 | security-review skill output | planned |
