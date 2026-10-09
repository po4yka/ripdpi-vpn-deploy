---
task_id: TFR-1791523370274374
change: provider-management-isolation
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No provider access authorized for this source PR.
staging: not_applicable
staging_evidence: No infrastructure deployment authorized for this source PR.
live: not_applicable
live_evidence: Source PR only; fleet behavior remains unverified.
client: not_applicable
client_evidence: Source PR only; client-path acceptance remains unverified.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PMI-SSH | TFR-1791523579427434 | Complete native management tests and range-aware policy tests | passed targeted checks; full gate pending |
| REQ-PMI-IDENTITY | TFR-1791523580174419 | Mock state transitions, unchanged plans and exact prevent_destroy diagnostics | passed targeted checks; full gate pending |
| REQ-PMI-HETZNER | TFR-1791523580174419 | Current-type plans and non-destructive attachment ownership migration | passed targeted checks; full gate pending |
| REQ-PMI-POLICY | TFR-1791523580836950 | Real Conftest positive/negative/empty evaluation and saved-plan subprocess tests | passed targeted checks; full gate pending |

## Delivery gates

TFR-1791523581450706 requires the complete local gate, independent security
review, an exact committed head, a scoped PR and reported hosted status.

## Observed targeted evidence

- Terraform 1.15.2 complete native suites: UpCloud 61, Hetzner 46, Vultr 46,
  Scaleway 39; all passed. Actual synthetic legacy/current state transitions:
  18 passed, including first adoption, protected key/name edits and safe forgetting.
- Real Conftest and operator snapshot/cleanup regressions: 52 passed.
- Policy unit tests: 46 passed. Independent security review: APPROVE after
  all-port selector and full UpCloud source-interval repairs.
- Full local check replay is running with real SOPS/age binaries and the working
  local Docker engine; prior portable run had 5294 passes and three launcher
  trust failures, and all three failures passed after correcting PATH.
- Draft PR is published; complete local and exact-head hosted results remain
  required before marking it ready. All commit hooks passed with pinned native
  ShellCheck execution.
