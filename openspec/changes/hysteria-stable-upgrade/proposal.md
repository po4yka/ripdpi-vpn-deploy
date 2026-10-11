# Change: Upgrade Hysteria with validated congestion and UDP resource profiles

Task ID: `SCR-1791618064422507`

## Why

The example still pins Hysteria v2.9.0 while the researched stable candidate is app/v2.13.0. Current bandwidth and QUIC windows are fixed and baseline lacks explicit UDP buffer controls. A pin-only edit would not prove real secure clients, hopping, resource limits, runtime adoption or rollback, nor establish whether supported congestion settings improve the selected technical path.

Audit coverage: A09, A22; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Revalidate candidate app/v2.13.0 release identity, publication time, release API status, advisories and architecture hashes at execution time; refresh every pin and consumer only after reviewed eligibility.
- Upgrade exact Hysteria artifacts through existing runtime-release ownership and exercise real process adoption and complete failure compensation.
- Expose typed exact-version-supported congestion, bandwidth and QUIC receive-window settings with paired client contracts and technical named profiles.
- Add baseline-owned typed UDP buffer ceilings and measured acceptance for sustained throughput, receive drops, latency, reconnects and multiple-client fairness.

## Capabilities

### New Capabilities

- `transports/hysteria-stable-runtime`: upgrade hysteria with validated congestion and udp resource profiles.

### Modified Capabilities

- None.

## Impact

- secrets/prod.secrets.example.yaml
- secrets/schema.json
- scripts/validate-secrets.py
- scripts/bootstrap-secrets.sh
- scripts/ci-bootstrap-secrets.sh
- ansible/roles/hysteria/defaults/main.yml
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/CLAUDE.md
- ansible/roles/baseline/defaults/main.yml
- ansible/roles/baseline/templates/sysctl-vpn.conf.j2
- ansible/roles/baseline/CLAUDE.md
- scripts/emit-singbox.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- tests/unit/test_hysteria_runtime_release.py
- tests/unit/test_runtime_audit_regressions.py
- docs/CLIENT-NOTES.md
- docs/TESTING.md
- .github/workflows/reproducible-build.yml
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
