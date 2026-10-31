---
id: SEC-1793428979810694
title: Encrypt node-side destination DNS resolution
kind: feature
status: doing
area: security
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793428979810694-encrypt-node-side-destination-dns-resolution
created: 2026-10-31
updated: 2026-10-31
related_tasks: []
---

## Goal

An observer on the VPS uplink sees no plaintext DNS from the host's own lookups when systemd-resolved is present: baseline installs a strict DNS-over-TLS drop-in with explicit servers and a fail-closed proof, and strict egress admits TCP/853. Recipient destination resolution is owned by SEC-1793428673775693 (loopback forwarder on the direct gateway); this task closes the host-side gap it left out of scope. DNS-Morph's port-53 ownership and the deferred stub restoration stay unchanged.

## Acceptance criteria

- Baseline installs the strict DoT drop-in only where resolved exists, restarts resolved through the existing transition task, proves one lookup, and withdraws the drop-in with a categorical failure when the proof fails.
- Strict egress admits TCP/853; snapshot goldens reflect it.
- The resolver round-trip tests, the runtime-audit resolver cases and the firewall egress tests pass; `make snapshot-check` passes.
