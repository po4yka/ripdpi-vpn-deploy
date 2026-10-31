---
task_id: MON-1793445381777509
change: mon-1793445381777509-point-the-nginx-403-detectors-at-the-decoy-vhost-logs
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Template, script and test change only; no private deployment plan is authorized.
staging: not_applicable
staging_evidence: No staging host is authorized for this change.
live: not_applicable
live_evidence: No provider, credential or live runtime mutation is included.
client: not_applicable
client_evidence: No client artifact or bundle contract changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-NGX403-VHOST-SOURCE | MON-1793445429481835 | `tests/unit/test_watchdog_templates.py` runs the rendered pipeline over temporary vhost logs; `make molecule-test ROLE=watchdog` | pending |
| REQ-NGX403-SUMMARY-SOURCE | MON-1793445430745409 | Aggregator unit test over a temporary log directory; `make check -j 4` | pending |
