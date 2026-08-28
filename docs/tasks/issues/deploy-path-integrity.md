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
updated: 2026-08-27
related_tasks: []
status_detail: Implementation remains on codex/complete-high-review at 37f3a6a50b21e294e5da6048a491d91568cd4627, not main. The bounded exact-source P0/P2 live-inventory dry-run passed on 2026-08-27; P2 used the existing private canonical-origin override. Recovery restored access. Live wait/rotation/rollback acceptance still requires a separately coordinated staging window.
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
