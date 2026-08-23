---
task_id: SEC-1787489155988233
change: sec-1787489155988233-client-config-registry
commit_sha: a80a032
local: passed
local_evidence: "make ci-fast green in worktree (actionlint, zizmor 1.29.0, cloud-init schema, tf-test 20+18+20+17 bats passed, yamllint, pytest 962 passed / 2 skipped incl. new test_client_registry.py and test_client_drift.py, shellcheck); taskctl validate (11 tasks, 53 steps); openspec validate 8/8; governance count updated to (1017 collected)."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: "No Terraform or Ansible changes; nothing to dry-run."
staging: not_applicable
staging_evidence: "No server-side behavior change; delivery host untouched."
live: required
live_evidence: null
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REGISTRY-RECORD | SCR-1787489427509997 | `make ci-fast` incl. coverage-check unit tests; missing-field fixture fails naming the device | pending |
| REQ-REGISTRY-LIFECYCLE | SCT-1787489427528995 | pytest of issuance/status transitions on a fixture secrets document | pending |
| REQ-REFRESH-OPTIONS | SCT-1787489427528995 | refresh option-resolution matrix tests (registered reuse, override echo, unregistered fail-closed); shellcheck clean | pending |
| REQ-PRIVATE-KEY-RECOVERY | SCR-1787489427509997 | test: private key present in encrypted document after generation; live shred-and-recover run below | pending |
| REQ-DRIFT-CHECK | TST-1787489427553290 | verdict-matrix unit tests (`current`/`stale`/`unknown`) and snapshot tests; `make client-drift` gate | pending |
| REQ-REGISTRY-SECURITY | DOC-1787489427574672 | grep proof that registry fields appear only in SOPS-gated paths; revocation flow test | pending |

## Evidence categories

### Local

Required. `make ci-fast` green on the implementation commit, including new
coverage, option-resolution, and drift-verdict tests.

### Remote CI

Required. Branch CI workflow green (shellcheck, pytest, gitleaks) before
merge.

### Dry-run

Not required — no Terraform or Ansible changes.

### Staging

Not required — no server-side behavior change; delivery host untouched.

### Live

Required. Onboard one test device against the production fleet, then:
shred `secrets/local/clients/<device>/**`, decrypt-recover the AWG key,
`make client-drift CLIENT=<device>` → `current`, force an outputs change →
`stale`, refresh via registry-resolved options, revoke → fetch returns
revoked response.

### Client

Required. One device imports the refreshed subscription payload and confirms
the expected format/hosts are active (no default single-host singbox
fallback).

### Artifact

Required. Registry rendering snapshot fixtures committed with tests; audit
log entries showing reused vs overridden options retained as redacted
evidence in the task record.
