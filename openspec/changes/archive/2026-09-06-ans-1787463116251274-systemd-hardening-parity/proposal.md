# Change: Align systemd hardening across internet-facing transports

Task ID: `ANS-1787463116251274`

## Why

The configuration audit found the systemd sandbox diverging across the three
internet-facing transport units. `hysteria-realm` carries the strongest
baseline (kernel-surface protections, `MemoryDenyWriteExecute`,
`SystemCallFilter` allowlist); plain `hysteria` lacks the write-execution and
syscall filters entirely, and `snell` — a research-tier but internet-facing
listener — additionally lacks the kernel-surface protections. A weaker sandbox
on any listener widens the blast radius of a parser exploit in exactly the
services exposed to hostile traffic.

## What Changes

- `hysteria-server.service.j2` gains `MemoryDenyWriteExecute=true` and the
  `SystemCallFilter=@system-service` allowlist with `@privileged @resources`
  denials, matching hysteria-realm.
- `snell.service.j2` additionally gains `ProtectKernelTunables=yes`,
  `ProtectKernelModules=yes`, `ProtectControlGroups=yes`, and
  `RestrictNamespaces=yes`.
- hysteria-realm's unit is already at the target baseline and is unchanged.
- No service arguments, ports, users, or restart policy change.

## Capabilities

### New Capabilities

- `ansible/transport-service-sandbox`: The minimum systemd sandbox every
  internet-facing transport unit must carry.

### Modified Capabilities

- None (unit hardening parity; no prior main spec exists for service sandbox
  baselines)

## Impact

- Deployed `hysteria` and `snell` systemd units on nodes running those roles.
- Molecule scenarios for both roles must still converge and verify.
- Known risk: an over-tight syscall filter can break a binary at runtime; both
  services run as non-root with CAP_NET_BIND_SERVICE only, the same profile
  already proven by hysteria-realm's sing-box processes.
