# ANS-1791996027408136: Recover interrupted ingress deploys and bind operator verbs to one node

## Objective

The next deploy after an interrupted protected ingress transaction compensates through the existing rescue and stops with a categorical message; dry-run reports it without mutation. `rotate-credentials`, `rollback-xray` and `rollback-config` act on exactly one named inventory alias, and rotation only within the selected environment. Operator runtime rollback is tested at its ownership boundary and documented truthfully. Implementation is authorized for source and portable/native validation; provider, inventory, SSH and live actions are outside scope.

## Ownership

Code lanes own disjoint paths and may run concurrently in one worktree; shared documents are edited by one lane after them.

- ANS-1791996166387223: `ansible/roles/nginx-xhttp/files/nginx_transaction.py`, `ansible/playbooks/tasks/transport-ingress-begin.yml`, `tests/unit/test_nginx_site_transaction.py`, `tests/unit/test_transport_site_transaction.py`, `ansible/roles/nginx-xhttp/CLAUDE.md`, `.agents/skills/vpn-deploy/SKILL.md`.
- ANS-1791996166966887: `Makefile`, NEW `ansible/playbooks/tasks/exact-node.yml`, `ansible/playbooks/rotate-credentials.yml`, `ansible/playbooks/rollback-xray.yml`, `ansible/playbooks/rollback-config.yml`, NEW `tests/unit/test_operator_verb_scope.py`, `tests/unit/test_transport_semantics.py`, `scripts/new-client.sh`, `README.md`, `docs/RUNBOOK-rotate.md`, `docs/SECRETS.md`, `scripts/CLAUDE.md`.
- ANS-1791996167525402: `ansible/roles/runtime-release/files/transport_runtime_rollback.py`, `tests/unit/test_transport_runtime_adapter.py`, `tests/unit/test_transport_runtime_acceptance_native.py`, `ansible/roles/runtime-release/CLAUDE.md`.
- Shared documents lane (after the code lanes): `docs/RUNBOOK-deploy.md`, `docs/RUNBOOK-rollback.md`, `docs/XRAY-RELEASE-LINE.md`, `ansible/CLAUDE.md`, `tests/CLAUDE.md`.

## Execution

- [x] ANS-1791996166387223 Adopt interrupted protected ingress journals into the existing rescue and recover pending-only publication journals at capture, with helper and Ansible harness tests #bug !high @item:ANS-1791996027408136
- [x] ANS-1791996166966887 Bind rotate-credentials, rollback-xray and rollback-config to one exact inventory alias and the selected environment, with real-Ansible and Make surface tests and updated operator docs #bug !high @item:ANS-1791996027408136
- [ ] ANS-1791996167525402 Pin the operator runtime rollback candidate set and ownership boundary with portable and native tests and correct the rollback documentation #bug !high @item:ANS-1791996027408136

## Verification

- Local: `mise exec -- python3 -m pytest tests/unit/test_nginx_site_transaction.py tests/unit/test_transport_site_transaction.py tests/unit/test_operator_verb_scope.py tests/unit/test_transport_semantics.py tests/unit/test_transport_runtime_adapter.py tests/unit/test_operator_admission.py tests/unit/test_backup_integrity_contract.py tests/unit/test_agent_instructions.py tests/unit/test_governance_counts.py -q`; `ansible-lint` on the changed playbooks and task files; `make shellcheck`; `make check`.
- Remote CI: required checks on the PR head, including the native runtime lane for the strengthened rollback assertions.
- Dry-run, staging, live, client: not applicable; no inventory, SSH or provider action is authorized.
- Artifacts: rendered snapshots and task/OpenSpec contracts pass at the frozen source.
