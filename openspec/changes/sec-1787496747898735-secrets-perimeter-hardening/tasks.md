# SEC-1787496747898735: Close secrets-handling and perimeter hardening gaps

## Objective

Secret-bearing renders never reach logs, every root scheduled unit carries the sandbox floor, perimeter ICMP follows the documented shaping floor, scheduled work uses systemd timers, external repository keys are pinned mandatorily, browser-facing vhosts share one header baseline, and rate limiting is enforced at exactly one documented layer.

## Ownership

- The primary agent owns tasks/templates of roles dns-morph-bridge, backup, geodata, firewall, cdn-front, warp-outbound, subscription-host, nginx-xhttp; the security-verify playbook assertions; and the two convention skill texts if the carve-out decision is taken.
- Serialized shared-file lane: none; role directories are exclusively owned within this change.

## Execution

- [x] SEC-1787496118906943 Add no_log: true and diff: false to the dns-morph-bridge bridge-config render task, matching the repo-wide secret-render discipline #bug !high @item:SEC-1787496747898735
- [x] SEC-1787496118906423 Convert vpn-backup.service and vpn-geodata-refresh.service from inline copy blocks to templates carrying the hardening floor (NoNewPrivileges, ProtectSystem, PrivateTmp and peers) with minimal ReadWritePaths; validate units with systemd-analyze verify in molecule #bug !high @item:SEC-1787496747898735
- [x] SEC-1787496118907048 Replace blanket ICMP accepts with rate-limited echo-request rules per family plus explicit accepts for required non-echo ICMPv6 types; add a security-verify assertion for the limit clauses #bug !high @item:SEC-1787496747898735
- [x] SEC-1787496118907149 Ship cdn-front-prefix-refresh.service + .timer (Persistent=true, jittered) replacing /etc/cron.daily/cdn-front-refresh-cf-prefixes; remove the cron file in the same converge #bug !high @item:SEC-1787496747898735
- [x] SEC-1787496118907052 Make the WARP repository signing key pin mandatory: ship a real default sha256 or fail closed when unset, keeping the existing verify/assert block as enforcement #bug !high @item:SEC-1787496747898735
- [x] SEC-1787496118906540 Align subscription vhost response headers with the public-site vhost (CSP tuned to static recipient pages, X-Content-Type-Options, Permissions-Policy, always flag) #bug !low @item:SEC-1787496747898735
- [x] SEC-1787496118906790 Resolve rate-limit layering: migrate both nginx limit_req zones behind the nftables policy-ratelimit layer OR amend the convention text with documented per-vhost exceptions and rationale; implement the chosen side consistently #chore !low @item:SEC-1787496747898735
- [ ] SEC-1787496118907178 Run named gates: molecule scenarios for touched roles, security-verify playbook in check mode, make ci-fast, make validate #test !high @item:SEC-1787496747898735

## Verification

Use the exact gates and evidence categories in `verification.md`.
