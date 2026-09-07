---
id: OPS-1787496414433523
title: "Harden deploy-path integrity: guards, rollback, rotation"
kind: bug
status: blocked
area: operations
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1787496414433523-deploy-path-integrity
created: 2026-08-23
updated: 2026-09-01
related_tasks: []
status_detail: All source steps are integrated. A bounded 2026-09-06 passive recheck returned unknown/command-failed for all three inventory aliases; the only online Tailnet peer is not an inventory endpoint, and the strict SSH-context mapping is unavailable. The required dry-run and live deploy-path cycle remains open.
---

## Goal

The operator deploy path enforces its own guarantees on every invocation shape: guards run under any tag scope, deploys wait for bootstrap completion, renderer inputs fail closed at plan time, rotation keeps the rollback restore point current, rollback validates before repointing runtime, failed probes reclaim resources, and maintenance gates depend only on repo-managed facts and locale-independent output. See openspec/changes/ops-1787496414433523-deploy-path-integrity/.

## Acceptance criteria

- All fourteen execution steps in the linked change are checked with recorded evidence.
- Named pytest cases cover tagged guards, renderer rejections, rollback ordering, rotation .prev creation, and toggle-default parity.
- A full deploy-path cycle (wait gate, rotation, rollback rehearsal) completes on live inventory; `make ci-fast`/`make validate` green.

## Narrow implementation ownership — 2026-08-28

- The inventory-guards agent owns only `scripts/render-inventory.sh`, its existing `tests/unit/test_render_inventory.py` coverage, and the relevant `scripts/CLAUDE.md` guidance in `codex/high-inventory-guards-20260828`.
- This slice covers steps `OPS-1787496118906369` and `OPS-1787496118906901`: reject unknown cohort profiles and duplicate inventory aliases without replacing the last valid inventory. Its tests use isolated local Terraform output fixtures, not provider or SSH access.
- The primary agent retains all other source, integration, and live acceptance ownership. The task remains blocked pending the remaining deploy-path work and required acceptance; this slice does not authorize deployment or close the task.

## Tagged-guard implementation ownership — 2026-08-28

- The primary agent owns only the five existing safety pre-task tags in `ansible/playbooks/site.yml` and their real-Ansible local regression coverage in `tests/unit/test_listener_contract.py` on `codex/high-tagged-guards-20260828`.
- This slice covers `OPS-1787496118906514`; it does not change role defaults, SSH migration, firewall policy, or live runtime. The inventory-guards slice and backup configuration work remain separate, and the overall task stays open.

## SSH allowlist implementation ownership — 2026-08-28

- The allowlist agent owns only `allowed_ssh_cidrs` validation in the four `terraform/providers/*/variables.tf` files, their existing `tests/firewall.tftest.hcl` regression cases, and this step's task/evidence notes on `codex/high-ssh-allowlist-20260828`.
- This slice covers `OPS-1787496118906156`; the matching `site.yml` nonempty assertion and always-tag coverage already exist in the base commit. Provider firewall rules, activation, SSH ports, runtime, tfvars, state, inventory, and other agents' source remain outside this slice.
- Validation uses native Terraform mock-provider plans only. Hosted checks and the parent task's remaining live acceptance are separate; this slice does not authorize apply or close the task.

## Xray restore-point implementation ownership — 2026-08-28

- The primary agent owns only `rollback-xray.yml`, the Xray portion of `rotate-credentials.yml`, the existing Xray/XHTTP regression module and matching runbook guidance in `codex/high-xray-restore-points-20260828`.
- Steps `OPS-1787496118906340` and `OPS-1787496118906432` have local source-behavior proof; full/hosted checks and staging/live acceptance remain separate. No host rotation, binary rollback or restart was performed.

## Bounded smoke implementation ownership — 2026-08-28

- The smoke agent owns `ansible/playbooks/smoke-test.yml`, focused local Ansible smoke regression coverage, and the relevant existing planning/evidence for `OPS-1787496118906646` in `codex/high-smoke-cleanup-20260828`. The shared playbook implements cleanup and subscription-only gating together; the two portfolio records retain their separate acceptance boundaries.
- Other playbooks, transport defaults/ports, Make, SSH, backup, production and other worktrees remain outside this slice. Source tests use temporary local executables; no host/provider operation or whole-task close is authorized here. The primary agent retains integration, generated board/counts and live acceptance.

## Bounded bootstrap wait ownership — 2026-08-28

- The bounded-wait agent owns only `scripts/wait-cloud-init.sh`, its existing `tests/unit/test_render_inventory.py` coverage, brief `scripts/CLAUDE.md` guidance, and evidence for `OPS-1787496118906208` in `codex/high-bootstrap-wait-20260828`.
- This slice preserves Terraform output routing and SSH identity, port, and trust policy. Make deploy integration, transport migration, backup configuration, shared board/count updates, and live acceptance remain with their existing owners. The overall task remains blocked.

## Inventory-bound readiness ownership — 2026-08-28

- The readiness agent owns `scripts/deploy-controller.py`, shared `scripts/bootstrap_readiness.py`, the narrow `scripts/wait-cloud-init.sh` adapter, deploy/dry-run Make dispatch and matching literal inputs, focused controller/Make/wait tests, and relevant runbook/scripts guidance on `codex/high-deploy-readiness-20260828` from `7b6622c6b6e34f4b89e0336f5a2aff264b85175f`.
- Step `OPS-1787496118906556` uses one private canonical-inventory selection for readiness, convergence and source parity. `fleet_inspection.py` APIs, backup configuration, SSH migration, provider/host operations and other agents' worktrees are outside this ownership. Shared integration, broad gates, board/count changes and live acceptance remain serialized by the primary agent; this task is not closed by local fixtures.

## Maintenance guard ownership — 2026-08-28

- The maintenance agent owns only `ansible/playbooks/os-maintenance.yml`, its existing `tests/unit/test_os_maintenance_contract.py` coverage, and this task's corresponding evidence on `codex/high-maintenance-guards-20260828`, based on main `bdc6b5a9c7f3d47b801341eba5560171ce41b589`.
- Steps `OPS-1787496118906956` and `OPS-1787496118906614` remove the external service from the unconditional health check and make the residual package simulation locale-independent. Local Ansible task-slice tests replace only OS command executables; they never run real package, service or reboot operations.
- Integration, all other deploy-path changes, and live rolling maintenance remain with their existing owners. These two source fixes do not close the parent task.

## Toggle-default ownership — 2026-08-28

- After the maintenance slice, the same agent owns ordinary transport fallback corrections in `site.yml`, `verify.yml`, `smoke-test.yml`, `os-maintenance.yml` and `rotate-credentials.yml`, plus disabled cascade declarations in `ansible/group_vars/all.yml`, existing profile/cascade tests, and corresponding evidence for steps `OPS-1787496118906821` and `OPS-1787496118906731`.
- Backup configuration prerequisites, baseline/SSH code, all role behavior and other agents' playbook changes remain untouched. Integration must preserve the already-reviewed smoke, verification and rotation changes in the primary agent's combined tree; this slice does not authorize live operations.
