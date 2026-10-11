# Change: Make REALITY target validation bounded standards-correct and truthful

Task ID: `SCR-1791617975137354`

## Why

The target validator describes ordinary curl with a Chrome User-Agent as browser ClientHello compatibility, manually accepts overly broad wildcard SAN suffixes, removes commas instead of splitting configured names and runs TLS work without deadlines. Target hygiene and filtered reachability are distinct, and owned self-steal targets need validation through their public service path rather than a remote sentinel's loopback.

Audit coverage: A20; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Normalize configured SNI names once and validate each with standards-correct certificate and handshake checks.
- Bound DNS TLS HTTP and metadata work with per-operation and overall deadlines and categorical failure output.
- Label ordinary curl as HTTP/TLS hygiene only and require an actual pinned compatible client for any browser ClientHello claim.
- Make borrowed public target and owned self-steal public-path validation explicit without changing target selection or secrets.

## Capabilities

### New Capabilities

- `transports/reality-target-validation`: make reality target validation bounded standards-correct and truthful.

### Modified Capabilities

- None.

## Impact

- scripts/validate-reality-target.sh
- scripts/monitor-reality-target.sh
- scripts/reality_target_monitor.py
- scripts/scan-reality-targets.sh
- scripts/CLAUDE.md
- docs/REALITY-TARGET-MONITORING.md
- ansible/roles/reality-self-steal/CLAUDE.md
- tests/unit/test_monitor_reality_target.py
- tests/unit/test_scan_reality_targets.py
- NEW: tests/unit/test_validate_reality_target.py
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
