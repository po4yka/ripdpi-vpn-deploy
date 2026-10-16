# ANS-1791996786767919: Close the window between protected ingress commit and egress finish

## Objective

An interruption anywhere in the protected commit leaves ingress and egress at one accepted generation after the next run.

## Ownership

- `ansible/playbooks/tasks/transport-ingress-commit.yml`, `ansible/playbooks/tasks/transport-ingress-begin.yml`, `ansible/roles/nginx-xhttp/files/nginx_transaction.py`, `ansible/roles/runtime-release/files/transport_runtime_outer.py`, the site transaction harness and native lane tests.

## Execution

- [x] ANS-1791996824479999 Make protected ingress commit and egress finish one recoverable boundary with SIGKILL tests at every interruption point #bug @item:ANS-1791996786767919

## Verification

- Local SIGKILL boundary tests; `make check`.
- Remote CI including the native transport lane.
