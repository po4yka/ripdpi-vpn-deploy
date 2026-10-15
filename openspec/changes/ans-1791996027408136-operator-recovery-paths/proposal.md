# Change: Recover interrupted ingress deploys and bind operator verbs to one node

Task ID: `ANS-1791996027408136`

## Why

A deep static audit of `1987d292`, re-verified at `82b14824` on 2026-10-14, found that the operator incident paths are the least protected part of the deployment lifecycle.

- A deploy interrupted between protected ingress capture and commit (Ctrl-C, lost SSH, the controller's 3600 s kill) leaves the nginx site journal on the node. The next `begin` and every check-mode admission refuse with `recovery-required`, and nothing in the repository calls the existing `--site restore` outside the same run's rescue. Every later dry-run and deploy fails, and the accepted egress generation that `begin` stopped can stay down until someone hand-builds a restore request.
- `make rotate-credentials`, `make rollback-xray` and `make rollback-config` pass no `--limit`, and their plays target `hosts: vpn` with no serial or single-host assertion. Ansible has no `ANSIBLE_LIMIT` setting, so the documented `ANSIBLE_LIMIT=<alias>` is ignored and the verbs mutate every inventory host in parallel. Credential rotation can also apply one environment's secrets to hosts rendered for another.
- Upstream `ab21b7fc` fixed the original `rollback-xray` release-identity defect for `xray.service`, but the runtime rollback branch has no portable test, the native lane does not prove the executable the unit runs, and the rollback documentation still describes symlink-only rollback and a nonexistent `.prev` binary.

## What Changes

- An interrupted protected ingress transaction found at the start of the next deploy is adopted into the existing single compensation sequence (quiesce candidate transports, restore the accepted ingress, roll back the egress generation). The deploy then ends non-zero with a categorical message; the operator repeats dry-run and deploy. Check mode refuses with the same category and mutates nothing.
- A recognized ordinary publication journal left without a site journal is recovered by the next site capture under the unit lock, as the ordinary publisher already does on its next entry. Unknown or foreign journals still refuse.
- BREAKING: `rotate-credentials`, `rollback-xray` and `rollback-config` require `ANSIBLE_LIMIT=<exact inventory alias>`, pass it as `--limit`, and their plays refuse unless exactly that one host is selected. Credential revocation is complete only after every node of the environment has been rotated, one invocation per node.
- BREAKING: `rotate-credentials` additionally requires clean source, the deploy pre-checks, and an inventory host whose `env` equals `ENV`.
- The runtime rollback branch gets portable tests for its candidate set and ownership boundary, the native lane asserts the rolled-back unit text and live executable, and the runbooks state that operator runtime rollback moves `xray.service` only.

## Capabilities

### New Capabilities

- `operations/operator-recovery-paths`: next-run recovery of interrupted protected ingress, exact-node targeting for operator incident verbs, and the documented scope of operator runtime rollback.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/nginx-xhttp/files/nginx_transaction.py`, `ansible/playbooks/tasks/transport-ingress-begin.yml`, `ansible/playbooks/site.yml` (rescue terminal message), NEW `ansible/playbooks/tasks/exact-node.yml`, `ansible/playbooks/rotate-credentials.yml`, `ansible/playbooks/rollback-xray.yml`, `ansible/playbooks/rollback-config.yml`, NEW `ansible/roles/transport-egress/tasks/helper-authority.yml` (the existing root-owned helper admission moved with an unchanged body), `ansible/roles/transport-egress/tasks/runtime-prepare.yml` (imports it in place of the moved task), `ansible/roles/runtime-release/files/transport_runtime_rollback.py` (behaviour-preserving extraction).
- Make interface (`Makefile`): `rotate-credentials`, `rollback-xray`, `rollback-config`, NEW `require-exact-node`, the literal alias capture and single-invocation guard that precede them, help text.
- vpnd: `vpnd/src/vpnd/runner/ansible.py` (`rotate()` takes one exact alias), `vpnd/tests/test_runner.py`.
- Tests: `tests/unit/test_nginx_site_transaction.py`, `tests/unit/test_transport_site_transaction.py`, NEW `tests/unit/test_operator_verb_scope.py`, `tests/unit/test_transport_semantics.py`, `tests/unit/test_transport_runtime_adapter.py`, `tests/unit/test_transport_runtime_acceptance_native.py`.
- Docs and agent guidance: `README.md`, `docs/RUNBOOK-deploy.md`, `docs/RUNBOOK-rotate.md`, `docs/RUNBOOK-rollback.md`, `docs/RUNBOOK-incident.md`, `docs/REGRESSION-BASELINE.md`, `docs/SECRETS.md`, `docs/XRAY-RELEASE-LINE.md`, `.agents/skills/vpn-deploy/SKILL.md`, and the `CLAUDE.md` files of `ansible/`, `ansible/roles/nginx-xhttp/`, `ansible/roles/runtime-release/`, `ansible/roles/transport-egress/`, `scripts/`, `tests/` and `vpnd/`.
- Task bookkeeping: `docs/tasks/board.md`, `docs/tasks/issues/operator-recovery-paths.md`, the tracked-separately follow-ups `docs/tasks/issues/gateway-runtime-rollback.md` and `docs/tasks/issues/ingress-egress-commit-window.md` with their OpenSpec changes, and the follow-up for the remaining operator-supplied Make variables, `docs/tasks/issues/make-variable-literal-capture.md` with its execution file `docs/tasks/work/SCR-1792057680449496.md`.
- Scope: source implementation and portable plus native-lane validation. Provider actions, inventory, SSH and live deployment remain outside scope.
- Out of scope, tracked separately: moving the private gateway units under the runtime rollback plan, and the cross-journal window between ingress commit and egress finish introduced by `ab21b7fc`.
