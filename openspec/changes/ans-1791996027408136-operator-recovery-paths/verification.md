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
| REQ-OPS-ORP-INGRESS-ADOPT | ANS-1791996166387223 | Ansible harness cases in tests/unit/test_transport_site_transaction.py for open, absent, malformed and check-mode site journals; passed locally: 32 harness cases including open, absent, malformed, outer-status refusal and check-mode journals; new cases fail against the unmodified playbooks | passed |
| REQ-OPS-ORP-PENDING-RECOVER | ANS-1791996166387223 | Helper cases in tests/unit/test_nginx_site_transaction.py for pending-only recovery, foreign pending refusal and check-mode refusal; passed locally: 54 helper cases including pending-only recovery, foreign and unrecognized journal refusal and check-mode refusal; 6 new cases fail against the unmodified helper | passed |
| REQ-OPS-ORP-EXACT-NODE | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py real-Ansible guard runs and Make surface checks; passed locally: real ansible-playbook guard runs for all three plays (no limit, list, group, pattern refuse; exact alias passes) and Make surface checks | passed |
| REQ-OPS-ORP-ROTATE-ENV | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py environment mismatch case and Make prerequisite checks; runbook text; passed locally: environment mismatch and missing-env refusals, Make prerequisites, runbook revocation text | passed |
| REQ-OPS-ORP-RUNTIME-ROLLBACK-SCOPE | ANS-1791996167525402 | tests/unit/test_transport_runtime_adapter.py candidate and ownership cases; native lane assertions in tests/unit/test_transport_runtime_acceptance_native.py; portable candidate and ownership cases passed locally; native lane assertions pending CI | pending |
