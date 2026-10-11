# Change: Detect client payload drift from every consumed private input

Task ID: `SCR-1791618188806822`

## Why

client-drift.py compares source and selected Terraform output hashes but does not consume the SOPS-owned material that can change a delivered payload. The existing main specification already requires re-rendering current inputs.

Audit coverage: A19; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Bind delivery identity to the canonical per-device rendered payload and recorded issuance options.
- Detect credential, endpoint, cohort, transport parameter and expiry changes without retaining plaintext payloads.
- Keep unconsumed credential/metadata edits from causing false stale verdicts.

## Capabilities

### New Capabilities

- `clients/payload-identity`: detect client payload drift from every consumed private input.

### Modified Capabilities

- `clients/config-registry`: correct the inherited consumed-input behavior with all existing callers updated.

## Impact

- scripts/client-drift.py
- scripts/issue-sub-token.sh
- scripts/emit-bundle.sh
- scripts/emit-awg.sh
- scripts/emit-singbox.sh
- secrets/schema.json
- tests/unit/test_client_drift.py
- tests/unit/test_client_registry.py
- openspec/specs/clients/config-registry/spec.md
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
