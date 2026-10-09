---
task_id: SEC-1791545689674403
change: ansible-role-p1-remediation
commit_sha: null
local: required
local_evidence: Pending role behavior, snapshots and full local gate.
remote_ci: required
remote_ci_evidence: Pending exact-source PR checks.
dry_run: not_applicable
dry_run_evidence: Source remediation only; no real inventory or SSH controller mutation.
staging: not_applicable
staging_evidence: This PR does not own a provider rollout or live notification.
live: not_applicable
live_evidence: Production deployment is outside the requested source PR.
client: not_applicable
client_evidence: Local transport/runtime regressions are not external client acceptance.
artifact: required
artifact_evidence: Pending reviewed source diff and PR artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-P1-XRAY | SEC-1791545814181293 | Safe log setup and rotation/geodata regressions | pending |
| REQ-P1-SUBSCRIPTION | SEC-1791545814181293 | Missing-state restart and verbose bearer redaction | pending |
| REQ-P1-BACKUP | SEC-1791545814181293 | Real local profile-scoped backup/integrity | pending |
| REQ-P1-RECEIVER | SEC-1791545814693187 | TLS admission and replay epoch tests | pending |
| REQ-P1-WATCHDOG | SEC-1791545815210908 | Stalled destination and synthetic process metadata tests | pending |
| REQ-P1-EXISTING | SEC-1791545815774612 | Existing resolver and isolated collector activation regressions | pending |
| REQ-P1-XRAY | SEC-1791545816326788 | Full local gates and independent security review | pending |
| REQ-P1-SUBSCRIPTION | SEC-1791545816326788 | Exact-source PR checks | pending |
