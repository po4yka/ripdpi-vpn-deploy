# role: hysteria-realm — P5 rendezvous service for UDP hole-punching

## Design decisions

Disabled role intent stops only declared owned services and removes exact runtime
configuration; shared packages, immutable release receipts and unrelated state
remain. The unique `hysteria_realm_role_enabled` selector defaults true for direct calls.

Explicit TLS-sharing overrides remain valid in standalone role use without a `vpn` mapping; fallback lookup normalizes the absent mapping before reading its Hysteria toggle.

**Native config validation precedes publication** — the template uses the
pinned `sing-box-realm check -c` command, so malformed candidates never replace
the active config or queue a restart.

**Rendezvous, not data plane** — the realm service mediates the endpoint
exchange between two sing-box peers and then drops out. The VPN data plane
never traverses this VPS; only the small TLS-wrapped handshake does.
The exact pinned service exposes a concurrent realm quota, `max_realms`
(default 16), for its technical control user; it does not expose the former
invented per-minute event field.

**Sing-box on both sides** — sing-box upstream does not (as of the pinned
tag) support asymmetric deployment against mainline `apernet/hysteria`.
Server and client must both run sing-box ≥ the pinned tag. Downgrading the
server tag without downgrading clients breaks the handshake silently.

**Alpha-tier pin is deliberate** — `hysteria_realm.version` lands on an
alpha release because that is where realm-service ships. The role reads
the version + sha256 from `hysteria_realm_secrets.linux_*_sha256` so a
version bump touches only the secrets file. Treat every minor bump as a
breaking change until upstream cuts a stable line.

**TLS ownership follows the enabled profile** — `share_hysteria_tls` defaults
to `vpn.enable_hysteria`. Co-hosted P2/P5 reuse the hysteria role's cert/key;
standalone P5 publishes its own PEM copies without requiring P2 files or
accounts. An explicit override is still respected. Supplementary
`hysteria` membership and `append` are enabled together only for shared TLS;
Ansible rejects `append: true` without a `groups` argument.

TLS destinations stay inside the role's config directory. Retirement removes
those configured copies or links and preserves shared Hysteria source material.

## What's done well

- **Shared runtime publication** — `runtime-release` verifies the pinned
  sing-box tarball, extracts only its architecture-bound member, records the
  installed digest, and publishes `current`, public, and `previous` links as
  one compensated transaction.
- **`MemoryDenyWriteExecute=yes` in the systemd unit** — sing-box is a
  static Go binary so JIT pressure does not apply; lock down W^X.

## Pitfalls

- **Sing-box realm-service schema is alpha and may change** — the rendered
  `config.json` uses the top-level services registry and hysteria-realm type
  with name/token/max_realms users at the exact pinned tag. A
  schema rename upstream means the role will emit a config sing-box
  refuses. Prereleases require inventory env=staging before any host mutation; omitted
  or production environment refuses. Verify the exact native parser and
  authenticated rendezvous protocol, not JSON syntax alone. The currently
  supported exact version is v1.14.0-alpha.22; a future pin requires a reviewed
  source/parser/protocol contract update before installation is allowed.
- **Auth token rotation invalidates every peer** — `hysteria_realm_
  secrets.auth_token` is presented by every peer during handshake. Treat
  it as long-lived; rotate only on compromise and re-ship every peer
  config in a coordinated wave.
- **Port 8444 default collides with the subscription-host role** — both
  default to 8444. The global listener manifest guard rejects the pair before
  either role runs; operators that enable both on a single VPS must override
  one. The molecule scenario does not catch this because it
  exercises the realm role in isolation.
- **TCP/realm-service-port must be open on the hypervisor firewall** —
  UpCloud/Hetzner/Vultr default closed. The Ansible firewall role opens
  it inside the VM, but the cloud firewall is a separate layer; the
  Terraform provider must include the rule.
- **Shared-cert renewal restarts realm only via its own converge** — the
  symlink to the hysteria cert dir is stable, so Ansible sees no change when
  only the underlying PEM rotates; a hysteria-side restart does not reach
  this service. Re-run the realm role (or restart it manually) after
  rotating shared TLS material.
- **Hole-punch failure is silent at this tier** — if NAT mapping
  collapses between rendezvous and data-plane setup, the client sees a
  timeout, not a server-side error. Logs here will show a successful
  rendezvous and nothing further. Diagnose client-side.
