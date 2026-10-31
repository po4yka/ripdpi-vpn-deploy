---
task_id: SEC-1793428368283759
change: sec-1793428368283759-anonymize-decoy-site-nginx-access-logs
commit_sha: null
local: passed
local_evidence: pytest on tests/unit/test_public_site_contract.py, test_nginx_xhttp_bearer_logs.py, test_watchdog_templates.py and test_monitoring_logrotate.py (101 passed); make snapshot-update then make snapshot-check (168 goldens match); make task-check passed after the board was regenerated. make check -j 4 -k in the cloud container failed only on environment limits that reproduce identically on a clean origin/main worktree - vpnd installer and delivery tests refuse to run as root, bats secrets tests under the untrusted root HOME, and 29 unit tests in subscription-mirror, tailnet, ci-deployment, dhcpv6, failover, xray-log-authority, runtime-release and observability files that depend on non-root ownership; none touches the changed templates or tests.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Template and test change only; no private deployment plan is authorized.
staging: not_applicable
staging_evidence: No staging host is authorized for this change.
live: not_applicable
live_evidence: No provider, credential or live runtime mutation is included.
client: not_applicable
client_evidence: No client artifact or bundle contract changes.
artifact: passed
artifact_evidence: The refreshed nginx logrotate golden reviewed in the pull request diff; the two site goldens match the formats merged on main.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TMD-DECOY-LOG-ANON | SEC-1793428548231362 | `tests/unit/test_public_site_contract.py` (format content and every enabled access log naming `vpn_public`, merged from `main`; both site files loaded into one `nginx -t`), `tests/unit/test_reality_self_steal.py` (self-steal format), `make snapshot-check` | Passed locally; remote CI pending |
| REQ-TMD-DECOY-LOG-STATUS-FIELD | SEC-1793428548231362 | `tests/unit/test_watchdog_templates.py` runs the rendered detector `awk` over rendered-format lines | Passed locally; remote CI pending |
| REQ-TMD-NGINX-LOG-RETENTION | SEC-1793428549224587 | `tests/unit/test_monitoring_logrotate.py` asserts `rotate 7`; `make check -j 4` | Passed locally (environment-only failures recorded above); remote CI pending |
