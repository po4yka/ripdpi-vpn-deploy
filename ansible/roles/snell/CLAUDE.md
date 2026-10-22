# role: snell — staged Snell transport candidate

## Design decisions

Device revocation installs root start admission before arming its exact operation/digest and config/unit hash plan. The existing role writes while the service is stopped; activation validates native configuration and loaded PID under the retained transaction lock. Partial writes, process death or activation failure leave boot and unrelated convergence fenced until the identical operation resumes.

Credential strings use JSON serialization in both server and smoke templates.
Parsed PSKs and userkeys must match the canonical Python recipient values,
including quotes, backslashes, control characters and UTF-8 text. Matching
server and smoke corruption is not authentication evidence.

**Research only** — Snell is a staging evaluation surface, not a family-profile transport. `vpn.enable_snell` is false everywhere and the role is tagged RESEARCH. A lab host must explicitly list `snell` in `allow_research_roles`.

**One pinned binary, three server variants** — a single checksum-pinned sing-box release serves the v4-compatible stream and the v6 default/unshaped variants on separate TCP listeners. The shared `runtime-release` role owns extraction, receipts, and compensated current/public/previous link publication. Separate listeners keep evaluation attribution explicit without multiplying daemons.

**No automatic selection** — emitted Snell outbounds live in a nested `snell-evaluation` selector and never enter the primary `auto` urltest. Promotion requires a separate tier/policy change after field evidence and a stable upstream protocol release.

## What's done well

- Versioned release receipts plus shared link compensation keep ordinary
  activation failures from consuming the previous rollback target.
- `sing-box check` validates the rendered candidate before systemd restarts it.
- Configuration and logs are owned by a dedicated unprivileged user; the config is `0640` and never diffed or logged by Ansible.

## Pitfalls

- The pinned sing-box engine is stable `1.14.3`. Snell v6 remains a research
  protocol; engine stability does not authorize production or promotion. The role
  rejects `prod` before download for stable and prerelease engine pins.
- Molecule uses a synthetic binary only for lifecycle checks. Required native
  tests use the checksum-verified release with all three variants, wrong userkeys
  and observed fresh/reused transport connections. Synthetic service health does
  not prove protocol compatibility.
- Server version 5 pairs with client version 4 because sing-box does not expose a separate v5 client wire format.
- v6 traffic shaping is key-dependent. Do not generalize from one PSK; rotate across the documented evaluation sequence.

- Ordinary site convergence always invokes lifecycle reconciliation. The
  `snell_role_enabled` input selects enable or owned runtime retirement before
  secret/package guards. Disable stops units and removes only declared authority;
  shared packages, immutable runtime receipts, historical logs and recovery data
  remain available for a later explicit recovery.
