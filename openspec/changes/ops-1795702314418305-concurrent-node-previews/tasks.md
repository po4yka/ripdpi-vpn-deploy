# OPS-1795702314418305: Preview several nodes at once while deploys stay serial

## Objective

Previews of different nodes run at the same time from one worktree, each node allows one controller operation at a time on the operator machine, and deploys stay one at a time.

## Ownership

Single serialized lane. Scripts: `scripts/deploy-controller.py`, `scripts/DESIGN-NOTES.md`. Tests: `tests/unit/test_deploy_controller.py`. Docs: `docs/how-to/deploy.md`.

## Execution

- [ ] OPS-1795702489297777 Take per-node operation locks and the fleet deploy lock in the deploy controller with refusal and release tests #feature @item:OPS-1795702314418305
- [ ] OPS-1795702516853613 Document the concurrent preview recipe and lock refusals in the deploy runbook #feature @item:OPS-1795702314418305
- [ ] OPS-1795702550913675 Run concurrent previews of two production aliases from one worktree and record their durations #feature @item:OPS-1795702314418305

## Verification

- Local narrow checks: `python3 -m pytest tests/unit/test_deploy_controller.py`, `make docs-check`.
- Local gate: `make check`.
- Remote: PR CI on the exact head SHA.
- Dry-run: concurrent timed previews of two production aliases from one worktree, each with its own secrets and inventory paths, and a refused preview of an alias that a deploy holds.
- Staging, live and client: not applicable; remote behaviour of a preview or a deploy does not change.
