# role: naive — NaiveProxy transport (optional)

## Design decisions

**Native validation and liveness are one lifecycle** — Caddyfile publication
uses the pinned caddy-naive `validate` command and the restart handler waits for
the service to become active before convergence may succeed.

**Optional, off by default** — `vpn.enable_naive: false`. NaiveProxy is a
useful tactical option for HTTP/2 + Chromium TLS fingerprint, but its v147
preamble change (see `docs/CLIENT-NOTES.md`) burned an upgrade cycle.

**Mutually exclusive with nginx-xhttp** — both want 443/tcp; the global
listener manifest guard rejects the pair before any role runs. The role
runs caddy-naive standalone with its own cert (from SOPS) on port 443 —
there is no shared listener.

**Source identity is compound** — xcaddy, Caddy, and the forwardproxy module
pin form one shared runtime-build receipt. The receipt also binds the expected
installed binary SHA256; changing one pin rebuilds in a private project stage
and publishes only after the expected digest passes.

## What's done well

- **Pinned binary + version** — pinned per `docs/CLIENT-NOTES.md` because
  client/server version skew is a real breakage class here.
- **Padding leak fix is monitored** — sing-box ≤ 1.10 NaiveProxy padding leak
  is noted; the role bumps the client recommendation when applicable.

## Pitfalls

- **v147 preamble change is breaking** — clients on < v147 cannot connect to
  server on ≥ v147. Coordinate upgrades; staging environment exists for this.
- **Authentication is HTTP Basic over TLS** — credentials in SOPS; the
  generated config emits them via env so they don't sit in plain config.
- **Don't share the auth pair across clients** — one credential per device,
  same rule as VLESS UUIDs.
