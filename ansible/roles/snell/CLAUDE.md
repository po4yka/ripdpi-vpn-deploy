# role: snell — staged Snell transport candidate

## Design decisions

**Research only** — Snell is a staging evaluation surface, not a family-profile transport. `vpn.enable_snell` is false everywhere and the role is tagged RESEARCH. A lab host must explicitly list `snell` in `allow_research_roles`.

**One pinned binary, three server variants** — a single checksum-pinned sing-box release serves the v4-compatible stream and the v6 default/unshaped variants on separate TCP listeners. Separate listeners keep evaluation attribution explicit without multiplying daemons.

**No automatic selection** — emitted Snell outbounds live in a nested `snell-evaluation` selector and never enter the primary `auto` urltest. Promotion requires a separate tier/policy change after field evidence and a stable upstream release.

## What's done well

- Versioned release directories plus a `current` symlink keep rollback atomic.
- `sing-box check` validates the rendered candidate before systemd restarts it.
- Configuration and logs are owned by a dedicated unprivileged user; the config is `0640` and never diffed or logged by Ansible.

## Pitfalls

- The pinned `1.14.0-alpha` line is forbidden in `prod`; the role fails before download when a prerelease is selected there.
- Server version 5 pairs with client version 4 because sing-box does not expose a separate v5 client wire format.
- v6 traffic shaping is key-dependent. Do not generalize from one PSK; rotate across the documented evaluation sequence.
