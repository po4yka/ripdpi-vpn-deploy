# Change: Deliver topology-aware authenticated transport health and secure smoke probes

Task ID: `MON-1791618056169855`

## Why

Ordinary verification and watchdog still assume one legacy AWG interface, and Hysteria smoke omits enabled obfuscation and bypasses TLS verification. Effective cohorts and XHTTP backend ownership also need one consistent health model. Existing source fixes and synthetic service checks do not by themselves prove authenticated transport delivery or correct outage attribution.

Audit coverage: A16, A17, A22; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Resolve ordinary verification, watchdog and smoke target sets from effective REALITY cohorts, XHTTP front/backend ownership, Hysteria settings and all bound AWG instances.
- Render secure Hysteria smoke clients with matching SNI, trusted certificate verification and optional Salamander, preserving bounded process ownership and cleanup.
- Perform authenticated positive data-plane checks through canonical clients and distinguish transport, local listener, direct-control and target failures.
- Target recovery only at the failing owned runtime and preserve bounded restart budgets, redacted results and unchanged existing P0 cohort fixes.

## Capabilities

### New Capabilities

- `operations/topology-authenticated-probes`: deliver topology-aware authenticated transport health and secure smoke probes.

### Modified Capabilities

- None.

## Impact

- ansible/playbooks/verify.yml
- ansible/playbooks/smoke-test.yml
- ansible/playbooks/os-maintenance.yml
- ansible/roles/watchdog/templates/vpn-watchdog.env.j2
- ansible/roles/watchdog/templates/vpn-watchdog.sh.j2
- ansible/roles/watchdog/CLAUDE.md
- ansible/templates/listener-manifest.json.j2
- scripts/liveness_profiles.py
- scripts/protocol-liveness.py
- scripts/check-liveness-profile-compatibility.py
- tests/unit/test_watchdog_templates.py
- tests/unit/test_watchdog_protocol_probe.py
- tests/unit/test_smoke_test_cleanup.py
- tests/unit/test_runtime_audit_regressions.py
- tests/unit/test_protocol_liveness_sentinel.py
- docs/TESTING.md
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
