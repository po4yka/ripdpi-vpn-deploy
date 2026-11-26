# Design: concurrent node previews

## Context

One controller run already keeps its working state private: `scripts/deploy-controller.py` copies the decrypted secrets, the selected inventory line, the known-host pins, the SSH key and every generated playbook into a run-owned temporary directory, sets `ANSIBLE_HOME` inside it, and creates SSH control sockets in a separate run-owned `/tmp/vd-ssh-*` directory. Two controller processes therefore share no written controller state.

The shared local state that blocks concurrent previews from one checkout is outside the controller:

| State | Why it collides | Isolation |
|---|---|---|
| Canonical inventory `ansible/inventory/generated.ini` | The default `ANSIBLE_INVENTORY`. Operator runners copy a node's inventory there before a run, so a second run overwrites the first run's input. | Each preview passes an explicit `ANSIBLE_INVENTORY` path that it does not write; the controller reads it once into its private copy. |
| Decrypted secrets path `SECRETS_FILE` | Defaults to `$RUNTIME_DIR/vpn-$(ENV).secrets.yaml`. Two runs of one environment share it, and the first `make clean` deletes it under the second run. | Each preview uses its own `SECRETS_FILE` under a private per-run directory and cleans only that path. |
| SSH ControlMaster path | `ansible/ansible.cfg` names a shared default, but the controller replaces the SSH arguments with a run-owned `%C` socket directory. | Already isolated by the controller; no change. |
| Ansible home and local temporary files | Already per run (`ANSIBLE_HOME` and `TMPDIR` inside the run directory). | No change. |
| Checkout | The controller binds the source identity at start and rechecks it before each host, and roles are read during the run. | One clean worktree at the reviewed revision serves all concurrent previews; nobody edits it while they run. One worktree per node is not needed. |

## Decisions

- Per-node exclusive operation lock, taken with a non-blocking `flock` on `<state>/locks/<alias>.lock` for each selected alias before the first readiness probe, and held until the controller exits. `<state>` is the operator state directory `${XDG_STATE_HOME:-$HOME/.local/state}/vpn-deploy`, mode `0700`, owned by the operator. The lock covers `dry-run` and `deploy`, because a preview of a node during its deploy reads a half-converged node and can report or refuse misleadingly.
- One fleet deploy lock (`<state>/locks/deploy.lock`, exclusive, non-blocking) for `deploy` only. It keeps deploys serial across worktrees and sessions. Previews never take it.
- Concurrency is per controller process, not inside one process. A controller run takes one secrets file for one environment, and production nodes use separate environments, so one run cannot preview several production nodes.
- A lock refusal is categorical (`node-operation-in-progress`, `deploy-in-progress`) and happens before any SSH operation, decrypted-secrets copy or receipt.
- Concurrent previews share one failure mode: a management-route outage on the operator machine stops all of them at once. `OPS-1795702284251279` owns that stall.

## Alternatives rejected

- One worktree per node at the same revision: it isolates the inventory and the secrets path only by accident of their relative defaults, and it multiplies the source to keep identical. Explicit per-run paths isolate them directly.
- Parallel hosts inside one `dry-run` invocation: it needs one secrets file per environment and a merged output stream, and it would add a second execution mode to the controller for the same result.
- A lock on the node instead of the operator machine: `transaction.lock` already protects mutation on the node, and a remote lock would need its own recovery path after a lost connection.

## Rollback

Remove the lock acquisition and the runbook recipe. Previews then run serially as before; no remote state depends on the locks.
