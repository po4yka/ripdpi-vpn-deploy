---
task_id: ANS-1791996027408136
change: ans-1791996027408136-operator-recovery-paths
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No real inventory or SSH transaction is authorized or included.
staging: not_applicable
staging_evidence: Source and isolated test validation does not establish a staging rollout.
live: not_applicable
live_evidence: No production deployment is authorized or claimed.
client: not_applicable
client_evidence: No client payload, bundle or recipient surface changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-ORP-INGRESS-ADOPT | ANS-1791996166387223 | Ansible harness cases in tests/unit/test_transport_site_transaction.py for open, absent, malformed and check-mode site journals | pending |
| REQ-OPS-ORP-PENDING-RECOVER | ANS-1791996166387223 | Helper cases in tests/unit/test_nginx_site_transaction.py for pending-only recovery, foreign pending refusal and check-mode refusal | pending |
| REQ-OPS-ORP-EXACT-NODE | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py real-Ansible guard runs and Make surface checks | pending |
| REQ-OPS-ORP-ROTATE-ENV | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py environment mismatch case and Make prerequisite checks; runbook text | pending |
| REQ-OPS-ORP-RUNTIME-ROLLBACK-SCOPE | ANS-1791996167525402 | tests/unit/test_transport_runtime_adapter.py candidate and ownership cases; native lane assertions in tests/unit/test_transport_runtime_acceptance_native.py | pending |
