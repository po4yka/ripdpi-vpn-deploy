# role: naive — NaiveProxy transport (optional)

## Design decisions

Disabled role intent stops only declared owned services and removes exact runtime
configuration; shared packages, immutable release receipts and unrelated state
remain. The unique `naive_role_enabled` selector defaults true for direct calls.

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
The service enables HTTP/1.1 and HTTP/2 only. HTTP/3 is disabled, so Caddy
cannot acquire an undeclared UDP listener or collide with an enabled UDP
transport. This deliberately keeps the transport's contract TCP-only.

**Source identity is compound** — xcaddy, Caddy, and the forwardproxy module
pin form one shared runtime-build receipt. The receipt also binds the expected
installed binary SHA256; changing one pin rebuilds in a private project stage
and publishes only after the expected digest passes.

Both Caddy site addresses carry the explicit configured port. A bare hostname
would silently add TCP/443 when a non-default port is selected, bypassing the
listener manifest. Native exact-composite adaptation checks the sole listener.

## What's done well

- **Pinned binary + version** — pinned per `docs/CLIENT-NOTES.md` because
  client/server version skew is a real breakage class here.
- **Padding leak fix is monitored** — sing-box ≤ 1.13.7 NaiveProxy padding leak
  (fixed in 1.13.8, `docs/CLIENT-NOTES.md`) is noted; the role bumps the client recommendation when applicable.

## Pitfalls

- **v147 preamble change is breaking** — clients on < v147 cannot connect to
  server on ≥ v147. Coordinate upgrades; staging environment exists for this.
- **Authentication is HTTP Basic over TLS** — credentials come from SOPS and
  render inline into the Caddyfile (`basic_auth` line), owned `0640`
  root:naive. There is no env-delivery path; the render is `no_log` with diff
  disabled so the pair never reaches Ansible output.
- **Don't share the auth pair across clients** — one credential per device,
  same rule as VLESS UUIDs.
