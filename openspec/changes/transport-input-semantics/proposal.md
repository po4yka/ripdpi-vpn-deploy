# Change: Reject incoherent transport inputs before runtime mutation

Task ID: `SCT-1791617687019287`

## Why

Current JSON Schema and semantic checks accept a REALITY cohort without clients, invalid AWG parameter relationships, and Hysteria masquerade types the deployed validator refuses. This plan tightens the accepted contract instead of introducing unsupported modes.

Audit coverage: A18; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Require explicit cohort membership and cross-reference integrity.
- Validate effective AWG relationships for single and multiple instances before any privileged action.
- Restrict Hysteria masquerade to the existing owned HTTPS proxy contract.

## Capabilities

### New Capabilities

- `transport/input-semantics`: reject incoherent transport inputs before runtime mutation.

### Modified Capabilities

- None.

## Impact

- secrets/schema.json
- secrets/prod.secrets.example.yaml
- scripts/validate-secrets.py
- scripts/spot-check-secrets.py
- scripts/check-secrets-coverage.py
- ansible/roles/runtime-release/files/validate_yaml_mapping.py
- tests/unit/test_secrets_schema.py
- tests/unit/test_spot_check_secrets.py
- tests/unit/test_transport_config_lifecycle.py
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
