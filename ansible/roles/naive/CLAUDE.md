# role: naive — NaiveProxy transport (optional)

## Design decisions

Activation probes explicitly require TLS 1.2 or newer while preserving CA,
hostname, PID, executable and listener ownership checks. Log files need only
the service owner and root validator; no separate group reader is granted.

Disabled role intent stops only declared owned services and removes exact runtime
configuration; shared packages, immutable release receipts and unrelated state
remain. The unique `naive_role_enabled` selector defaults true for direct calls.

**Native validation and liveness are one lifecycle** — Native JSON publication
uses the pinned caddy-naive `validate` command. A private fsynced activation
receipt binds binary, unit, config and TLS digests. Missing/stale acknowledgement
forces synchronous restart and a verified local TLS handshake before success,
even if publication was interrupted and its bytes are now unchanged.

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

Native JSON declares one explicit TCP listener at the configured port; no
hostname auto-HTTPS address can acquire an undeclared port. Receipt readiness
binds the actual unit MainPID, executable inode, exact config argv and listening
socket ownership before/after the TLS handshake.

Per-device `clients` is explicit and permits zero entries for last-device
revocation. Names, usernames and passwords are independently unique. The pinned
plugin receives one native `auth_credentials` entry per device. Its byte-slice
JSON encoding preserves all schema-valid printable ASCII without Caddyfile
quoting or environment substitution. An empty list removes the whole
forward-proxy handler and retains the decoy, without an unauthenticated fallback.

## What's done well

- **Pinned binary + version** — pinned per `docs/CLIENT-NOTES.md` because
  client/server version skew is a real breakage class here.
- **Padding leak fix is monitored** — sing-box ≤ 1.13.7 NaiveProxy padding leak
  (fixed in 1.13.8, `docs/CLIENT-NOTES.md`) is noted; the role bumps the client recommendation when applicable.

## Pitfalls

- **Validation opens the default log writer** — root-run Caddy validation can
  create root-owned `0600` access and site-error logs before the service starts.
  Inspect retained log authority before directory metadata convergence, then
  provision the exact service-owned `0600` logs before validation, preserving
  bytes and refusing symlinks, hardlinks, unsafe ancestry and foreign owners.
  Existing root-owned safe logs from validation are migrated without truncation.

- **v147 preamble change is breaking** — clients on < v147 cannot connect to
  server on ≥ v147. Coordinate upgrades; staging environment exists for this.
- **Authentication is HTTP Basic over TLS** — credentials come from SOPS and
  render as native JSON byte-slice credentials into `caddy.json`, owned `0640`
  root:naive. There is no env-delivery path; the render is `no_log` with diff
  disabled so the pair never reaches Ansible output.
- **Don't share the auth pair across clients** — one credential per device,
  same rule as VLESS UUIDs.

The former credential-bearing `Caddyfile` is never a runtime fallback. A guarded
retirement recognizes only its former role-rendered footprint and exact private
metadata; it is unlinked durably after successful JSON adoption. Foreign files
refuse without deletion or restart. Disabled intent retires both known paths.
