# role: hysteria-realm — P5 rendezvous service for UDP hole-punching

## Design decisions

**Native config validation precedes publication** — the template uses the
pinned `sing-box-realm check -c` command, so malformed candidates never replace
the active config or queue a restart.

**Rendezvous, not data plane** — the realm service mediates the endpoint
exchange between two sing-box peers and then drops out. The VPN data plane
never traverses this VPS; only the small TLS-wrapped handshake does.
Operationally that means `hysteria_realm.events_per_minute_max` can be set
low (default 600/min) — a high handshake rate is itself anomalous and
should fail closed rather than absorb a flood.

**Sing-box on both sides** — sing-box upstream does not (as of the pinned
tag) support asymmetric deployment against mainline `apernet/hysteria`.
Server and client must both run sing-box ≥ the pinned tag. Downgrading the
server tag without downgrading clients breaks the handshake silently.

**Alpha-tier pin is deliberate** — `hysteria_realm.version` lands on an
alpha release because that is where realm-service ships. The role reads
the version + sha256 from `hysteria_realm_secrets.linux_*_sha256` so a
version bump touches only the secrets file. Treat every minor bump as a
breaking change until upstream cuts a stable line.

**Shared cert with the P2 hysteria role** — `share_hysteria_tls: true`
(default) symlinks the hysteria role's cert/key into this role's config
dir. One renewal path covers both tiers. Set to `false` to point at a
separately-managed cert when the operator splits hostnames. Supplementary
`hysteria` membership and `append` are enabled together only for shared TLS;
Ansible rejects `append: true` without a `groups` argument.

## What's done well

- **Shared runtime publication** — `runtime-release` verifies the pinned
  sing-box tarball, extracts only its architecture-bound member, records the
  installed digest, and publishes `current`, public, and `previous` links as
  one compensated transaction.
- **`MemoryDenyWriteExecute=true` in the systemd unit** — sing-box is a
  static Go binary so JIT pressure does not apply; lock down W^X.

## Pitfalls

- **Sing-box realm-service schema is alpha and may change** — the rendered
  `config.json` follows the upstream inbound shape at the pinned tag. A
  schema rename upstream means the role will emit a config sing-box
  refuses. Bump in staging only and run the molecule scenario.
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
