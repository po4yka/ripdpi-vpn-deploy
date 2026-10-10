# Change: Deliver coordinated Hysteria ECH server and recipient profiles

Task ID: `ANS-1791618083683925`

## Why

ECH is a grounded optional transport evolution, but the current server/client emission contract has no coordinated ECH authority, recipient capability check or real connection proof. A server-only option or unsupported-engine refusal would not deliver the feature and could break secure recipient connections.

Audit coverage: A17, A22; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Define one explicitly selected technical ECH profile binding supported server runtime, supported recipient engine, inner/outer identity and encrypted configuration generation.
- Model private ECH server authority in encrypted storage and public recipient material in a typed versioned contract, updating actual recipient parsers and canonical clients together.
- Deliver exact-runtime ECH secure connections and observably encrypted ClientHello behavior while preserving certificate validation, masquerade identity and required authenticated probes.
- Implement complete private authority/config activation and compensating rollback, with unsupported clients rejected before publication and compatible clients positively exercised.

## Capabilities

### New Capabilities

- `transports/hysteria-ech-profiles`: deliver coordinated hysteria ech server and recipient profiles.

### Modified Capabilities

- None.

## Impact

- ansible/roles/hysteria/defaults/main.yml
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/templates/hysteria-server.service.j2
- ansible/roles/hysteria/CLAUDE.md
- secrets/schema.json
- secrets/prod.secrets.example.yaml
- scripts/validate-secrets.py
- scripts/bootstrap-secrets.sh
- scripts/emit-singbox.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- scripts/check-liveness-profile-compatibility.py
- contract/ripdpi-bundle.schema.json
- ansible/playbooks/smoke-test.yml
- tests/unit/test_bundle_schema.py
- tests/unit/test_emit_singbox_roundtrip.py
- docs/CLIENT-NOTES.md
- docs/RIPDPI-BUNDLE.md
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
