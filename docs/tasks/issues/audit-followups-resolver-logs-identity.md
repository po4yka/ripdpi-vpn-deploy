---
id: SEC-1793428673775693
title: Close the remaining traffic-privacy audit findings on resolver privacy, decoy logs and identity checks
kind: bug
status: doing
area: security
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793428673775693-audit-followups-resolver-logs-identity
created: 2026-10-31
updated: 2026-10-31
related_tasks: []
---

## Goal

Recipient destination names never leave the node in plaintext DNS: the normalizer and the Xray frontend resolve through the direct gateway's loopback forwarder, which answers over DNS-over-HTTPS and drops non-address queries. The decoy and self-steal nginx sites keep access logs without client addresses or user agents. The watchdog detects a borrowed REALITY target that no longer completes the TLS 1.3, X25519, h2 handshake a client expects. A production host refuses a WireGuard-shaped AmneziaWG instance without a recorded measurement. REALITY inbounds listen dual-stack like the decoy, and the documentation states why shipped AmneziaWG cohorts carry no I1-I5 programs and why Hysteria bandwidth hints are identical per node.

## Acceptance criteria

- The built normalizer topology resolves through `127.0.0.2` except under DNS-Morph; the direct gateway renders a `dokodemo-door` inbound on that address, a `dns` outbound with `nonIPQuery: reject` and only `https+local://` DNS servers; kernel policy admits the gateway's port-53 replies toward 127.0.0.1 before its loopback deny, and only the direct gateway unit carries `CAP_NET_BIND_SERVICE`.
- The rendered Xray frontend uses `127.0.0.2` as its DNS server outside cascade and DNS-Morph profiles and listens on `::` for every REALITY inbound.
- Rendered nginx-xhttp and self-steal vhosts carry a `log_format` without `$remote_addr` or `$http_user_agent` and every enabled `access_log` uses it; the watchdog's status-column 403 counter keeps working.
- The watchdog environment carries `XRAY_REALITY_TARGET` and `XRAY_REALITY_SNI`, and the handshake probe returns 0 only for a trusted TLS 1.3 handshake that negotiates h2 (`reality_target_drift` otherwise).
- `guard-wireguard-shape.yml` refuses `env: prod` for an instance with `S1 = S2 = 0` and `H1..H4 = 1,2,3,4` unless `awg_wireguard_shaped_measurement` is set, and accepts staging, padded or random-header instances.
- `docs/reference/awg-cohorts.md` and `docs/reference/client-notes.md` state the I1-I5 and bandwidth-hint decisions; snapshot goldens and the narrow tests pass; CI is green at the pull-request head.
