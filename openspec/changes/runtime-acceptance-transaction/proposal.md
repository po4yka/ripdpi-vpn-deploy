# Change: Commit transport runtimes only after complete configuration and readiness acceptance

Task ID: `ANS-1791617913525586`

## Why

Shared runtime-release verifies owned bytes and compensates its link publication, but returns committed before Xray or Hysteria2 configuration and service readiness are accepted. A later parser, asset, certificate, bind or startup failure leaves the active links selecting a rejected runtime. Existing nginx and geodata publication improvements do not establish a complete transport runtime transaction.

Audit coverage: A04; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Extend the existing publication foundation with an explicit staged-candidate and consumer acceptance contract.
- Coordinate runtime, required assets, complete configuration, TLS and service state under one resource ownership boundary.
- Persist desired and accepted generations so interrupted activation and unchanged retries recover deterministically.
- Restore exact accepted authority after ordinary validation or readiness failure, with authenticated positive readiness proof.

## Capabilities

### New Capabilities

- `transports/runtime-acceptance-transaction`: commit transport runtimes only after complete configuration and readiness acceptance.

### Modified Capabilities

- None.

## Impact

- ansible/roles/warp-outbound/ (bounded process-disappearance retirement and CI refusal diagnostics)
- tests/unit/test_warp_pin_contract.py
- ansible/roles/observability_agent/ (sender activation and retained queue)
- tests/unit/test_observability_runtime_queue.py
- ansible/roles/runtime-release/tasks/main.yml
- ansible/roles/runtime-release/files/runtime_release_activate.py
- ansible/roles/runtime-release/CLAUDE.md
- ansible/roles/xray-runtime/tasks/main.yml
- ansible/roles/xray-runtime/CLAUDE.md
- ansible/roles/xray/tasks/enable.yml
- ansible/roles/xray/handlers/main.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/handlers/main.yml
- ansible/roles/hysteria/CLAUDE.md
- tests/unit/test_runtime_release_contract.py
- tests/unit/test_runtime_release_consumers.py
- tests/unit/test_hysteria_runtime_release.py
- NEW: tests/unit/test_transport_runtime_acceptance.py
- NEW: tests/integration/transport_runtime_acceptance/
- ansible/roles/runtime-release/files/transport_runtime_*.py
- ansible/roles/transport-egress/tasks/runtime-*.yml
- ansible/roles/transport-egress/tasks/begin.yml
- ansible/roles/transport-egress/tasks/rollback.yml
- ansible/roles/transport-egress/files/snapshot.py
- ansible/roles/geodata/
- ansible/playbooks/rollback-config.yml
- ansible/playbooks/rollback-xray.yml
- ansible/playbooks/tasks/transport-ingress-commit.yml
- ansible/molecule/
- tests/unit/test_transport_runtime_acceptance_native.py
- tests/unit/test_transport_runtime_adapter.py
- Makefile
- secrets/prod.secrets.example.yaml
- Scope: source implementation, isolated native validation and PR integration. Provider actions and deployment remain outside scope.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
