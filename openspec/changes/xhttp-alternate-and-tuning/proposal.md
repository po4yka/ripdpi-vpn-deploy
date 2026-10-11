# Change: Deliver selectable alternate XHTTP endpoints and measured typed tuning

Task ID: `XRY-1791617991738391`

## Why

The server exposes an optional alternate direct XHTTP frontend, but the recipient emitter advertises only the primary. XHTTP mode and advanced connection behavior are largely upstream defaults rather than a tested shared contract. The existing architecture can deliver explicit alternate selection and bounded performance profiles cheaply after endpoint correctness, isolation and safe runtime adoption are established.

Audit coverage: Upgrade or feature roadmap; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Export and select the enabled alternate XHTTP endpoint with its actual port owned hostname and verified TLS identity.
- Extend existing Xray-backed liveness profiles to observe each enabled endpoint and identify which path completed traffic.
- Expose only a reviewed typed subset of supported XHTTP mode and XMUX connection/request bounds shared by server and exact recipient engines.
- Measure positive transfer reconnect idle and failure behavior against the baseline before promoting a tuning profile; retain stable pins and classical P0 behavior.

## Capabilities

### New Capabilities

- `transports/xhttp-alternate-and-tuning`: deliver selectable alternate xhttp endpoints and measured typed tuning.

### Modified Capabilities

- None.

## Impact

- scripts/emit-singbox.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- secrets/schema.json
- scripts/validate-secrets.py
- ansible/roles/xray/templates/config.json.j2
- ansible/roles/xray/defaults/main.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/nginx-xhttp/tasks/enable.yml
- ansible/roles/nginx-xhttp/templates/site.conf.j2
- ansible/roles/nginx-xhttp/CLAUDE.md
- docs/CLIENT-NOTES.md
- docs/XRAY-RELEASE-LINE.md
- docs/PQ-REALITY-ADOPTION.md
- tests/unit/test_liveness_profiles.py
- tests/unit/test_relay_fallback.py
- tests/unit/test_secrets_schema.py
- NEW: tests/unit/test_xhttp_alternate_profiles.py
- NEW: tests/integration/xhttp_delivery_matrix/
- NEW: docs/XHTTP-DELIVERY-PROFILES.md
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
