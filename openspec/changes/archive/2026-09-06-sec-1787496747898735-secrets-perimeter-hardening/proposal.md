# Change: Close secrets-handling and perimeter hardening gaps

Task ID: `SEC-1787496747898735`

## Why

The audit found one secret-exposure defect and six hardening deviations from the repo's own stated conventions: the dns-morph-bridge signing-key render lacks log suppression (the only secret-bearing render in the tree without it, and the key is the most expensive to rotate), two root systemd units run with zero sandboxing against the declared hardening floor, ICMP is admitted unrate-limited contrary to the hardening skill floor, the cdn-front prefix refresh runs from root cron.daily against the no-root-cron hard rule, the WARP repository key is the only artifact fetched without a mandatory pin, the subscription vhost ships a weaker response-header set than its sibling public vhost while serving operator-built HTML, and nginx-layer rate limiting contradicts the documented nftables enforcement convention.

## What Changes

- The dns-morph-bridge config render task gains `no_log: true` and `diff: false`.
- `vpn-backup.service` and `vpn-geodata-refresh.service` move from inline copy blocks to hardened unit templates carrying the standard floor plus minimal ReadWritePaths.
- Firewall input policy rate-limits ICMP echo per family while preserving required ICMPv6 neighbor-discovery and PMTUD types.
- The cdn-front refresh schedule moves to a systemd service+timer (Persistent=true) and the cron.daily file is removed in the same converge.
- The WARP repository signing key pin becomes mandatory (fail closed when unset).
- The subscription vhost gains CSP/X-Content-Type-Options/Permissions-Policy aligned with the public-site vhost.
- Rate limiting lands on exactly one layer: either the two nginx zones are migrated to the firewall layer or the convention text is amended with documented exceptions — decided in design before implementation.

## Capabilities

### New Capabilities

- `security/perimeter-hardening`: Observable contract for secrets-log discipline on renders, the systemd sandbox floor for root scheduled units, shaped ICMP handling at the perimeter, timer-based scheduling, mandatory supply-chain pins for external repositories, uniform response-header baseline on browser-facing vhosts, and single-layer rate-limit enforcement.

### Modified Capabilities

- None

## Impact

- Ansible roles: dns-morph-bridge, backup, geodata, firewall (+ security-verify assertion), cdn-front, warp-outbound, subscription-host, nginx-xhttp.
- docs: linux-hardening/nginx-configuration convention texts reconciled with implementation.
- Related but non-blocking: ANS-1787463116251274 (transport unit sandbox parity — this change covers the remaining zero-hardening inline units).
