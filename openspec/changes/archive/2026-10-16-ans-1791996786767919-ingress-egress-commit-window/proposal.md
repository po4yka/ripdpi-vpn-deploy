# Change: Close the window between protected ingress commit and egress finish

Task ID: `ANS-1791996786767919`

## Why

`ansible/playbooks/tasks/transport-ingress-commit.yml` runs `--site commit` (which removes the nginx site journal) and then the egress outer `finish` as two separate steps, an order introduced by `ab21b7fc`. A deploy killed between them leaves ingress committed at the new generation while the egress outer route is still open; the next run's egress recovery rolls egress back to the previous generation, so ingress and egress serve different generations. Reversing the order only moves the window: with ANS-1791996027408136 an open site journal is adopted and restored while egress has already finished. Found while re-verifying audit finding H1 on 2026-10-14.

## What Changes

- Commit of the protected site becomes atomic across the ingress and egress journals: after an interruption at any point, the next run either completes both or restores both to the previously accepted generation.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `operations/operator-recovery-paths`: interrupted commit recovery covers both journals as one boundary.

## Impact

- Ansible: `ansible/playbooks/tasks/transport-ingress-commit.yml`, `ansible/playbooks/tasks/transport-ingress-begin.yml`, `ansible/roles/nginx-xhttp/files/nginx_transaction.py`, `ansible/roles/runtime-release/files/transport_runtime_outer.py`.
- Tests: SIGKILL-between-commit-steps cases in the site transaction harness and native lane.
- Depends on ANS-1791996027408136 (site journal adoption).
