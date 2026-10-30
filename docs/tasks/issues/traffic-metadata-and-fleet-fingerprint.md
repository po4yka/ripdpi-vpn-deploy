---
id: SEC-1793386547449444
title: Close traffic-metadata retention and fleet-fingerprint audit findings
kind: bug
status: doing
area: security
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793386547449444-traffic-metadata-and-fleet-fingerprint
created: 2026-10-30
updated: 2026-10-30
related_tasks: []
---

## Goal

A default node keeps no per-connection device, address or destination record (Xray access log off unless the policy rate-limiter needs it; Hysteria at `warn`). A production P1 host serves an operator-owned decoy, answers XHTTP upstream errors with that decoy's 404, and the secrets example no longer carries a deployable XHTTP path. REALITY validation reports X25519 and SNI-to-address consistency, self-steal refuses a shared hostname with a different certificate, and emitted sing-box clients probe latency every 30 minutes.

## Acceptance criteria

- Rendered Xray configuration carries `"access": "none"` for every profile with `enable_policy_ratelimit: false`, and the Hysteria unit carries `HYSTERIA_LOG_LEVEL=warn`.
- nginx-xhttp refuses `env: prod` without `nginx_xhttp_public_site_dir`, publishes an operator tree at the same relative paths, and both XHTTP locations answer 404/502/503/504 upstream results with status 404 and `/404.html`.
- `make validate-secrets` in strict mode refuses the example `xhttp_path` placeholder.
- The validator reports `x25519_unavailable` and `sni_resolves_elsewhere` from real fixtures without printing names; self-steal fails on a shared hostname with distinct certificates.
- Emitted sing-box `auto` outbound uses `interval: 30m`; snapshot goldens and `make check` pass; CI is green at the pull-request head.
