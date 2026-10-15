# Change: Deliver authoritative AmneziaWG device enrollment and client bindings

Task ID: `SCR-1791618039091425`

## Why

The deployed role treats a nonempty instance collection as authoritative, while enrollment and public emitters still write or read the legacy top-level peer collection and fixed address pool. Issuance can therefore succeed with a peer absent from the deployed server, emit the wrong endpoint and parameters, or silently omit an enabled AWG profile.

Audit coverage: A05, A06; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Introduce one effective instance and device binding contract consumed by role normalization, enrollment, revocation, standalone configuration emission, RIPDPI bundle emission and liveness.
- Select the effective listener, server key, technical cohort and address pool from the same authoritative host/profile data as deployment rather than hard-coded or unused secret fallbacks.
- Allocate and revoke per-device peer material in the selected encrypted instance under the existing credential lock, preserving unrelated devices and transport collections.
- Reject ambiguous or missing bindings and unsupported parameter relationships before mutation or issuance; enabled transports cannot silently disappear from output.

## Capabilities

### New Capabilities

- `transports/awg-device-binding`: deliver authoritative amneziawg device enrollment and client bindings.

### Modified Capabilities

- None.

## Impact

- scripts/new-client.sh
- scripts/rotate-secrets.sh
- scripts/emit-awg.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/validate-secrets.py
- secrets/schema.json
- secrets/prod.secrets.example.yaml
- ansible/roles/amneziawg/tasks/instances.yml
- scripts/ripdpi_cohort_fingerprint.py
- contract/cohort-fingerprint.golden.json
- contract/ripdpi-bundle.schema.json
- tests/unit/test_emit_bundle_host_selection.py
- tests/unit/test_bootstrap_awg_handoff.py
- tests/unit/test_secrets_schema.py
- docs/AWG-COHORTS.md
- docs/RIPDPI-BUNDLE.md
- scripts/CLAUDE.md
- ansible/roles/amneziawg/CLAUDE.md
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
