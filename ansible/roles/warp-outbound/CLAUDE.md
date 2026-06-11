# role: warp-outbound — server egress through Cloudflare WARP

## Design decisions

**Health-gated activation** — `vpn.enable_warp_outbound` flips the toggle,
but the role only swings outbound routing *after* WARP confirms it's up.
Failure leaves the previous egress intact.

**SOCKS5 at 127.0.0.1:40000** — WARP runs in `proxy` mode; Xray's
`outbound.protocol: socks` points at it. Don't try kernel-level routing
through WARP — too easy to lock yourself out.

## What's done well

- **Reversible** — disabling the toggle and re-running puts outbound routing
  back. Tested in `RUNBOOK-rollback.md`.
- **Version-tolerant CLI** — both `warp-cli set-mode proxy` (old) and
  `warp-cli mode proxy` (new) are tried; the role doesn't pin to one syntax.

## Pitfalls

- **WARP packages have a Cloudflare repo with a key rotation history** —
  pin the apt-key once and don't auto-refresh; manual update via the
  release-line tracker.
- **WARP and IPv6 don't get along on some kernels** — disable v6 on the WARP
  interface if you see ICMPv6 floods.
- **`warp-cli register` runs unattended-only on first boot** — if it fails
  mid-deploy, manual `warp-cli register` is needed before re-running.
- **WARP changes egress IP** — anything keying on the server's public IPv4
  (asn-drift, burn-check) sees a different reality through WARP. Probes must
  account for this when WARP is on.
- **On-host health check is vantage-limited — does not confirm RU reachability** — the `warp=on` liveness check that the role performs runs from the VPS itself (non-RU vantage) and confirms only that the local WARP daemon is up and the SOCKS5 proxy responds. It does NOT verify that WARP egress survives RU ISP filtering. WARP's default transports (WireGuard UDP 2408/UDP 500, and the HTTP/2 fallback) were broadly blocked on RU ISPs by early 2026. Operators should verify WARP egress end-to-end from a filtered RU vantage after deployment and after any WARP version or config change; a clean on-host health check is a necessary but not sufficient signal.
