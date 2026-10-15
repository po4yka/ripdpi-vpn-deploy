---
task_id: ANS-1791996027408136
change: ans-1791996027408136-operator-recovery-paths
commit_sha: "f6ad803e97237d8d8ec3839284d84db974ea986c"
local: "passed"
local_evidence: "517 targeted recovery/operator/real-Ansible cases and 58 standalone adapter cases passed on Mac; snapshots and source lint passed. Full local make check failed on registry timeout; queued retry cancelled. Complete unchanged source CI supplies the approved full gate."
remote_ci: "passed"
remote_ci_evidence: "CI 38768887914 completed all 88 jobs successfully on f6ad803e97237d8d8ec3839284d84db974ea986c; complete native integration, AWG, XHTTP, runtime rollback and canonical monitoring scenarios passed. Required CodeQL checks succeeded on this source."
dry_run: not_applicable
dry_run_evidence: No real inventory or SSH transaction is authorized or included.
staging: not_applicable
staging_evidence: Source and isolated test validation does not establish a staging rollout.
live: not_applicable
live_evidence: No production deployment is authorized or claimed.
client: not_applicable
client_evidence: No client payload, bundle or recipient surface changes.
artifact: "passed"
artifact_evidence: "All 163 golden snapshots match; source schemas contracts and redacted exact-runtime acceptance artifacts passed."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-ORP-INGRESS-ADOPT | ANS-1791996166387223 | Ansible harness cases in tests/unit/test_transport_site_transaction.py for open, absent, malformed and check-mode site journals and for helper admission before the outer status runs; passed locally: 20 interrupted-journal cases under real ansible-playbook (open, closed, absent and absent-with-empty-state outer route, malformed with and without an open egress route, outer-status refusal, helper admission refusal of a symlinked, hard-linked or group-writable helper and a writable helper directory before status runs, a missing helper with a regular, dangling-symlink or directory `outer.json`, a symlinked, non-directory, mode 0755, mode 0777 or foreign-owned state directory (the harness expects the test user where production expects root) refusing as `egress-outer-helper-missing` before adoption with the journal retained and no compensation or helper run, the refusal naming the complete `transport_runtime_*.py` helper set and the production contract test pinning that set to the helper admission's, and check-mode journals) and the static production-contract test, within the file's 47 collected tests, 38 of which run real ansible-playbook and the rest being parser and static checks; the four helper admission cases and the eight missing-helper refusal cases fail against the unmodified playbooks (the latter adopt and compensate; the three unsafe state directory cases also fail against the playbook that accepted any plain directory without `outer.json`), while the malformed open-route and check-mode refusal cases and the two missing-helper cases with no route state pass against them and are added evidence for the documented stopped-transport, no-mutation and unchanged closed-route outcomes | passed |
| REQ-OPS-ORP-PENDING-RECOVER | ANS-1791996166387223 | Helper cases in tests/unit/test_nginx_site_transaction.py for pending-only recovery, foreign pending refusal and check-mode refusal; passed locally: 54 helper cases including pending-only recovery, foreign and unrecognized journal refusal and check-mode refusal; 6 new cases fail against the unmodified helper; harness case in tests/unit/test_transport_site_transaction.py for a pending-only journal: dry-run refuses with the distinct interrupted-nginx-publication category, states that the recovery deploy converges the complete graph unpreviewed, and mutates nothing, and one following deploy recovers it and converges, which fails against the unmodified playbook | passed |
| REQ-OPS-ORP-EXACT-NODE | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py real-Ansible guard runs and Make surface checks; passed locally: real ansible-playbook guard runs for all three plays (no limit, list, group, pattern refuse; exact alias passes) and Make surface checks | passed |
| REQ-OPS-ORP-ROTATE-ENV | ANS-1791996166966887 | tests/unit/test_operator_verb_scope.py environment mismatch case and Make prerequisite checks; runbook text; passed locally: environment mismatch and missing-env refusals, Make prerequisites, runbook revocation text | passed |
| REQ-OPS-ORP-RUNTIME-ROLLBACK-SCOPE | ANS-1791996167525402 | tests/unit/test_transport_runtime_adapter.py candidate and ownership cases; native lane assertions in tests/unit/test_transport_runtime_acceptance_native.py; portable candidate and ownership cases passed locally; native lane assertions passed at exact main source 923304729f6bdd32edce6a9b6ceada1d51c7d011 in CI 38759230876 job 116505845756 | passed |

## Integrated source verification (2026-10-15)

Exact main CI 38759230876 native transport job 116505845756 passed all 4 cases including rollback MainPID unit candidate-scope and reconvergence assertions. Source is `923304729f6bdd32edce6a9b6ceada1d51c7d011`; hosted logs were inspected directly. Full targeted real-Ansible/helper/operator suite passed 517 cases with no skips; standalone adapter 58 passed. Complete local make check pending. No external infrastructure or real notification action occurred.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.

## Final source acceptance (2026-10-15)

All unchanged hosted source consumers and native acceptance passed in CI 38768887914 on `f6ad803e97237d8d8ec3839284d84db974ea986c`. Focused Mac validation, snapshots and full-history secret scanning passed as recorded above. The owner-approved task scope accepts this combined source gate; the failed monolithic Mac invocation is not reclassified as passing. No external infrastructure or human notification receipt is claimed.
