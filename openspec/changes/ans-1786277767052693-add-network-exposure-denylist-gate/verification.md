---
task_id: ANS-1786277767052693
change: ans-1786277767052693-add-network-exposure-denylist-gate
commit_sha: 729f262588973c51650042dcffa405ac523354b1
local: passed
local_evidence: "Canonical make -j1 check passed on the exact source tree: 2729 Python tests passed with one existing skip, 55 BATS passed, 184 Rust tests and release Clippy passed, plus Terraform 87, Conftest 45, cloud-init, schema, render, security, and liveness gates. Log SHA256 ecdac36313e37515abc5e407748ebcba444650116f648e460054b6027cb2c907."
remote_ci: required
remote_ci_evidence: null
dry_run: passed
dry_run_evidence: "Controller and Molecule regressions exercise disabled parity, review-only and log-only outcomes, exact canary scoping, expiry refusal, redaction, and rollback without invoking firewall mutation."
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Live enforcement requires a later owner-authorized change.
client: not_applicable
client_evidence: No client behavior is owned by this change.
artifact: passed
artifact_evidence: "Schema-bound placeholder fixtures and reviewed artifacts are accepted only through exact digest/signature/host binding; hard links, symlinks, unsafe modes, foreign owners, and mutable parent paths fail closed. No production artifact or address data is committed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ANS-1786277767052693-001 | TST-1786277767052610 | Disabled render parity, invalid-input refusal, no-follow artifact checks, idempotence, and rollback regressions; canonical full gate passed | passed |
| REQ-ANS-1786277767052693-002 | ANS-1786277767052243 | Strict feed/policy/artifact validation precedes the disabled-default Ansible role; exact host and listener intent are bound before any handoff | passed |
| REQ-ANS-1786277767052693-003 | ANS-1786277767052018 | Versioned directional policy and feed metadata schemas use non-deployable placeholder examples and reject undeclared or ambiguous fields | passed |
| REQ-ANS-1786277767052693-004 | ANS-1786277767052707 | Review controller emits bounded redacted results for review-only, log-only, canary, expiry, and rollback states without applying firewall policy | passed |
| REQ-ANS-1786277767052693-005 | DOC-1786277767052241 | Operator documentation records reviewed-artifact refresh, promotion criteria, traffic scope, disabled default, and the absence of a hidden apply path | passed |

## Evidence boundary

This delivery implements the reviewed source gate only. It does not enable the
UpCloud firewall, modify a provider policy, deploy a denylist, or establish
staging traffic acceptance. Promotion remains a separately authorized change
with exact return-path and rollback evidence; PR110 remains draft and unsafe to
apply.
