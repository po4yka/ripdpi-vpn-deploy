---
task_id: ANS-1787463116251274
change: ans-1787463116251274-systemd-hardening-parity
commit_sha: null
local: passed
local_evidence: pytest tests/unit/test_transport_service_sandbox.py (2 passed) pins the baseline directive set on all three units; full pytest tests/unit green (941 passed); make validate green; local molecule blocked by arch mismatch (amd64-only pinned digest vs arm64 workstation) — CI runs the scenarios
remote_ci: blocked
remote_ci_evidence: pending required checks on the remediation PR; molecule (hysteria) and molecule-failure-scenarios cover the touched roles
dry_run: not_applicable
dry_run_evidence: no Terraform surface changes
staging: not_applicable
staging_evidence: sandbox parity is enforced by contract test and CI molecule convergence; no separate staging environment exists for unit directives
live: blocked
live_evidence: next converge on a hysteria/snell node applies the tightened units; record the run after merge
client: not_applicable
client_evidence: no client-facing emitter changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SANDBOX-BASELINE | ANS-1787463325958892 | Contract test asserting the baseline directive set on hysteria, hysteria-realm, snell unit templates | Pending |
| REQ-SANDBOX-BASELINE | ANS-1787463325959076 | molecule scenarios for hysteria and snell converge and verify with the tightened units | Pending |
