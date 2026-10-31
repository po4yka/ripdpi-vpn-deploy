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

An observer on the VPS uplink sees no per-destination DNS query in clear. The transport-egress normalizer resolves through the direct gateway's DoH forwarder behind an owned kernel redirect, the Xray frontend and private gateways render DoH servers with `unexpectedIPs`, and hosts with systemd-resolved use strict DoT with explicit servers and a fail-closed proof. DNS-Morph's port-53 ownership and the deferred stub restoration stay unchanged.

## Acceptance criteria

- The production egress context seals the normalizer to `127.0.0.1`, publishes `resolver.forwarder_port`, and the rendered policy contains the normalizer-only NAT redirect, admission drop, normalizer accept and gateway reply accept.
- The direct gateway answers forwarder A/AAAA queries over `https+local://` upstreams with `unexpectedIPs` and drops other query types; the non-cascade frontend renders DoH servers.
- Baseline installs the strict DoT drop-in only where resolved exists, proves one lookup after restart, and withdraws the drop-in with a categorical failure when the proof fails; strict egress admits TCP/853.
- The resolver round-trip tests, transport-egress unit tests, `make snapshot-check` and the native egress lanes in CI pass.
