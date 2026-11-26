# Change: Preview several nodes at once while deploys stay serial

Task ID: `OPS-1795702314418305`

## Why

A full-graph preview (`make dry-run ANSIBLE_LIMIT='<exact-alias>' ANSIBLE_TAGS=`) takes 17 to 57 minutes per production node, and a rollout previews each node in turn. The measurements in `OPS-1795697141240057` show that the time is a long tail of about 1,300 tasks, each costing one or more round trips over the management route; no single task dominates. Previews of different nodes share no remote state, so running them at the same time cuts the preview phase of a five-node rollout from the sum of the node times to about the time of the slowest node.

Two previews already ran at the same time from one checkout during that research, and they did not interfere locally. The same day, a preview and an operator's own preview of the same node also overlapped by accident, because nothing on the operator machine records which node an operation holds. Deploys must stay one node at a time: `site.yml` keeps `serial: 1`, each node keeps its `transaction.lock`, and recovery assumes exclusive use of the node.

## What Changes

- The deploy controller takes an exclusive per-node operation lock on the operator machine for each selected alias, in both `dry-run` and `deploy`. A second operation on the same alias refuses at once with a categorical error instead of overlapping. The lock lives in one operator state directory outside every checkout, so different worktrees coordinate.
- `deploy` also takes one exclusive fleet deploy lock, so a second deploy refuses even for another node. `dry-run` does not take it, so previews of other nodes can run beside a deploy.
- The deploy runbook gains a recipe that previews several aliases at once: one controller process per alias from one clean worktree at the reviewed revision, each with its own decrypted secrets path, its own explicit inventory path and its own log. `deploy`, `verify` and later stages keep the single-alias recipe.

## Capabilities

### New Capabilities

- `operations/concurrent-node-previews`: concurrent per-node previews with per-node operation locks; deploys stay serial.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/deploy-controller.py` (lock acquisition before the first SSH operation, release on every exit).
- Docs: `docs/how-to/deploy.md` (concurrent preview recipe, lock refusal), `scripts/DESIGN-NOTES.md`.
- Tests: controller tests for lock refusal, release after failure, and isolation of concurrent previews.
- No Ansible role, Terraform, secrets schema or client contract change. Remote behaviour of a preview or a deploy is unchanged.
