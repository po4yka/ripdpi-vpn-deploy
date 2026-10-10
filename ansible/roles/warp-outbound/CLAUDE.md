# role: warp-outbound — server egress through Cloudflare WARP

## Design decisions

**Recovery evidence exercises actual role outcomes** — Molecule's stateful CLI fixture changes only in response to real role commands, supports idempotence, and injects CLI and trace transport failures before successful reconvergence. `warp=off` remains rejected. No test increments an invented retry counter; this proves role reconvergence, not automatic vendor retries or live registration.

The role requires an explicit stable `package_version`, validates native APT
metadata, installs that exact dpkg version and checks the installed identity
before any registration, mode or route changes. Out-of-band installations must
also present the approved dpkg identity; no mutable latest-package selection remains.

**Health-gated activation** — `vpn.enable_warp_outbound` flips the toggle,
but the role only swings outbound routing *after* WARP confirms it's up.
Failure leaves the previous egress intact.
`site.yml` runs this gate before Xray, including `--tags xray`; a later
nginx handler flush must never activate unverified WARP routes first.

**SOCKS5 at 127.0.0.1:40000** — WARP runs in `proxy` mode; Xray's
`outbound.protocol: socks` points at it. Don't try kernel-level routing
through WARP — too easy to lock yourself out.

## What's done well

- **Reversible** — disabling the toggle and re-running puts outbound routing
  back.
- **Current CLI syntax only** — the role runs `warp-cli --accept-tos mode
  <mode>`; there is no fallback to the older `warp-cli set-mode` form.

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
- **On-host health is vantage-limited** — a successful local SOCKS check does not
  establish reachability from a filtered client path. That requires scoped client
  acceptance after deployment or a version/configuration change.
- Disable stops the vendor unit only when this role's private bounded ownership
  record claims it; registration, vendor package and recovery state are retained.
  An unrecorded prior vendor installation is preserved for explicit owner review.
