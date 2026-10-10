# Change: Upgrade pinned AmneziaWG sources with unchanged reviewed wire settings

Task ID: `SCR-1791618073850409`

## Why

Current examples pin Go v0.2.12 and tools v1.0.20241018, while researched candidate tags are v3.1.20260828 and v3.1.20260812. The source and client version gap requires semantic, toolchain and physical compatibility proof. Installed binary receipts and controller restart dispatch do not demonstrate warm running-process adoption or preserved real tunnel behavior.

Audit coverage: A07, A22; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Revalidate candidate Go and tools tags, immutable commits, publication/channel metadata, module and build toolchain requirements and reachable critical/high advisory status at execution time.
- Update exact source descriptors and every generator/fixture together, preserving receipt ownership, serialized build publication and coherent running-instance activation.
- Keep reviewed existing wire settings and S3/S4 zero while proving candidate interoperability with exact supported server/client versions and canonical binding/fingerprint inputs.
- Add real warm pin-only and unit-only adoption, reboot/reconnect, bidirectional data and physical Android arm64 candidate acceptance before promotion.

## Capabilities

### New Capabilities

- `transports/awg-source-runtime`: upgrade pinned amneziawg sources with unchanged reviewed wire settings.

### Modified Capabilities

- None.

## Impact

- secrets/prod.secrets.example.yaml
- scripts/bootstrap-secrets.sh
- scripts/ci-bootstrap-secrets.sh
- secrets/schema.json
- ansible/roles/amneziawg/tasks/enable.yml
- ansible/roles/amneziawg/templates/awg-quick@.service.j2
- ansible/roles/amneziawg/handlers/main.yml
- ansible/roles/amneziawg/CLAUDE.md
- ansible/roles/runtime-release/tasks/source-build.yml
- scripts/emit-sbom.py
- contract/cohort-fingerprint.golden.json
- contract/amneziawg-arm64-version-floor.json
- scripts/check-amneziawg-arm64-upstream.py
- tests/unit/test_amneziawg_source_pins.py
- tests/unit/test_amneziawg_native_lifecycle.py
- tests/unit/test_transport_p2_lifecycle.py
- tests/unit/test_amneziawg_version_floor.py
- docs/AWG-COHORTS.md
- docs/CLIENT-NOTES.md
- docs/TESTING.md
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
