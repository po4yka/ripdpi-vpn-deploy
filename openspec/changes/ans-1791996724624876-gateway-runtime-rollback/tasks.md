# ANS-1791996724624876: Roll back private gateway runtimes with the frontend runtime

## Objective

Operator runtime rollback moves the frontend and both private gateways to the previous release with one publisher per unit file and native executable proof.

## Ownership

- `ansible/roles/transport-egress/tasks/stage.yml`, `ansible/roles/transport-egress/files/generation.py`, `ansible/roles/transport-egress/templates/gateway.service.j2`, `ansible/roles/runtime-release/files/transport_runtime_rollback.py`, `ansible/roles/runtime-release/files/transport_runtime_accept.py`, `ansible/roles/runtime-release/files/transport_runtime_validate.py`, related unit and native tests, `docs/RUNBOOK-rollback.md`.

## Execution

- [ ] ANS-1791996772545665 Make the runtime rollback plan the single publisher of every unit that binds the pinned Xray release path, roll back both private gateways with the frontend, and prove each process executable natively #bug @item:ANS-1791996724624876

## Verification

- Local portable ownership and candidate tests; `make check`.
- Remote CI including the native runtime lane with rollback followed by an ordinary converge.
