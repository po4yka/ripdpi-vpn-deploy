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
| REQ-OPS-ORP-INGRESS-ADOPT | ANS-1791996166387223 | Ansible harness cases in tests/unit/test_transport_site_transaction.py for open, absent, malformed and check-mode site journals and for helper admission before the outer status runs; passed locally: 20 interrupted-journal cases under real ansible-playbook (open, closed, absent and absent-with-empty-state outer route, malformed with and without an open egress route, outer-status refusal, helper admission refusal of a symlinked, hard-linked or group-writable helper and a writable helper directory before status runs, a missing helper with a regular, dangling-symlink or directory `outer.json`, a symlinked, non-directory, mode 0755, mode 0777 or foreign-owned state directory (the harness expects the test user where production expects root) refusing as `egress-outer-helper-missing` before adoption with the journal retained and no compensation or helper run, the refusal naming the complete `transport_runtime_*.py` helper set and the production contract test pinning that set to the helper admission's, and check-mode journals) and the static production-contract test, within the file's 47 collected tests, 38 of which run real ansible-playbook and the rest being parser and static checks; the four helper admission cases and the eight missing-helper refusal cases fail against the unmodified playbooks (the latter adopt and compensate; the three unsafe state directory cases also fail against the playbook that accepted any plain directory without `outer.json`), while the malformed open-route and check-mode refusal cases and the two missing-helper cases with no route state pass against them and are added evidence for the documented stopped-transport, no-mutation and unchanged closed-route outcomes | passed |
| REQ-OPS-ORP-PENDING-RECOVER | ANS-1791996166387223 | Helper cases in tests/unit/test_nginx_site_transaction.py for pending-only recovery, foreign pending refusal and check-mode refusal; passed locally: 54 helper cases including pending-only recovery, foreign and unrecognized journal refusal and check-mode refusal; 6 new cases fail against the unmodified helper; harness case in tests/unit/test_transport_site_transaction.py for a pending-only journal: dry-run refuses with the distinct interrupted-nginx-publication category, states that the recovery deploy converges the complete graph unpreviewed, and mutates nothing, and one following deploy recovers it and converges, which fails against the unmodified playbook | passed |
| REQ-OPS-ORP-EXACT-NODE | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py real-Ansible guard runs and Make surface checks; passed locally: real ansible-playbook guard runs for all three plays (no limit, list, group, pattern refuse; exact alias passes) and Make surface checks | passed |
| REQ-OPS-ORP-ROTATE-ENV | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py environment mismatch case and Make prerequisite checks; runbook text; passed locally: environment mismatch and missing-env refusals, Make prerequisites, runbook revocation text | passed |
| REQ-OPS-ORP-RUNTIME-ROLLBACK-SCOPE | ANS-1791996167525402 | tests/unit/test_transport_runtime_adapter.py candidate and ownership cases; native lane assertions in tests/unit/test_transport_runtime_acceptance_native.py; portable candidate and ownership cases passed locally; native lane assertions pending CI | pending |
