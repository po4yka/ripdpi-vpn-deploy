# Change: Enforce resolved destination isolation for P0 P1 and Hysteria2

Task ID: `SEC-1791617841911853`

## Why

Xray still routes domain destinations through its unconditional direct rule before IPIfNonMatch resolution, allowing Freedom to resolve and dial private addresses afterward. Hysteria2 lacks an equivalent complete recipient destination boundary. These failures violate local management and private network isolation even though public forwarding is intended. Previously integrated role, firewall and lifecycle fixes do not implement this resolved-address policy.

Audit coverage: A01, A02; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Define one explicit recipient destination isolation policy for literal and resolved IPv4 and IPv6 addresses across REALITY, XHTTP and Hysteria2.
- Bind policy evaluation to the addresses actually dialed, including DNS retries and multi-address answers, without relying solely on an Xray routing strategy change.
- Preserve positive public TCP and supported UDP forwarding, intended DNS resolution and documented trusted adapter entry points.
- Add exact pinned-runtime positive and adversarial destination tests; retain privacy-safe failure diagnostics.
- Reuse pinned Xray private egress gateways and final nftables UID boundaries.
- Redesign optional WARP UDP through an isolated vendor tunnel-only backend, with no plaintext fallback and separate real-vendor acceptance.

## Capabilities

### New Capabilities

- `transports/resolved-destination-boundary`: enforce resolved destination isolation for p0 p1 and hysteria2.

### Modified Capabilities

- None.

## Impact

- ansible/roles/xray/templates/config.json.j2
- ansible/roles/xray/tasks/enable.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/CLAUDE.md
- scripts/validate-secrets.py
- tests/unit/test_secrets_schema.py
- NEW: tests/unit/test_transport_destination_boundary.py
- NEW: tests/integration/transport_destination_boundary/
- NEW: docs/TRANSPORT-DESTINATION-POLICY.md
- Current user authorization covers source implementation, isolated validation, local commits and a PR. Private-input mutation, provider registration and deployment remain separately authorized.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
