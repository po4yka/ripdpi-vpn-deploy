---
id: SEC-1794807596362904
title: Close baseline hardening gaps from the live fleet audit
kind: bug
status: doing
area: security
priority: medium
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1794807596362904-baseline-live-audit-hardening
created: 2026-11-16
updated: 2026-11-16
related_tasks: []
---

## Goal

Managed VPN nodes close the host-hardening gaps that the 2026-11-16 live fleet audit found: IPv6 redirect acceptance, runtime kernel replacement, an unhardened BPF JIT, a usable root password, unused distribution services, and a journal budget that cannot hold the configured retention.

## Acceptance criteria

- The baseline sysctl policy refuses IPv6 redirects, disables kexec image loading and hardens the BPF JIT; a host that cannot apply one of these keys fails convergence.
- The root account has a locked password after convergence, and key-based operator access is unchanged.
- `modemmanager`, `apport`, `open-vm-tools` and `snapd` are absent after convergence.
- The journal size budget is 1G with the 14-day retention unchanged.
- Tailscale update policy, nginx sandboxing, observer parity and live-only actions stay out of scope.
