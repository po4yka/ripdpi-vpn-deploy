---
task_id: MON-1793445381777509
change: mon-1793445381777509-point-the-nginx-403-detectors-at-the-decoy-vhost-logs
commit_sha: null
local: passed
local_evidence: pytest on tests/unit/test_watchdog_templates.py, tests/unit/test_probing_summary_remote.py and tests/unit/test_agent_instructions.py (47 passed); make snapshot-update refreshed the watchdog script golden and make snapshot-check reports 168 matching goldens; shellcheck on the rendered watchdog script adds no finding; make task-check passed after the board was regenerated. make check -j 4 -k in the cloud container failed only on environment limits that reproduce identically on a clean origin/main worktree (vpnd installer and delivery tests refuse to run as root, bats secrets tests under the root HOME, and 31 unit tests in subscription-mirror, tailnet, ci-deployment, dhcpv6, failover, xray-log-authority, runtime-release and observability files that depend on non-root ownership); none touches the watchdog, the aggregator or their tests. make molecule-test ROLE=watchdog needs a Docker daemon the container lacks; CI's molecule lane covers it.
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
artifact: passed
artifact_evidence: The refreshed watchdog script golden (tests/snapshot/golden/watchdog/templates/vpn-watchdog.sh.j2) reviewed in the pull request diff.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-NGX403-VHOST-SOURCE | MON-1793445429481835 | `tests/unit/test_watchdog_templates.py` runs the rendered pipeline over temporary vhost logs; `make molecule-test ROLE=watchdog` | Passed locally (rendered-pipeline test); molecule and remote CI pending |
| REQ-NGX403-SUMMARY-SOURCE | MON-1793445430745409 | Aggregator unit test over a temporary log directory; `make check -j 4` | Passed locally (environment-only failures recorded above); remote CI pending |
