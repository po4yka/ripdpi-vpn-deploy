---
title: Verify only Internet-exposed listeners
type: task
status: doing
area: ansible
priority: high
owner: Codex
parent: null
blocks: []
blocked_by: []
created: 2026-07-18
updated: 2026-07-18
---

# Verify only Internet-exposed listeners

- [ ] #task Verify only Internet-exposed listeners #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/doing ⏫

## Goal

Make the security verification distinguish Internet-exposed sockets from private control-plane and host-local listeners while continuing to fail when a required public service is loopback-only or an unexpected service is publicly reachable.

## Ship definition

- [ ] Required wildcard or public-address listeners satisfy the manifest contract.
- [ ] Loopback-only and private-address-only listeners do not satisfy a public listener requirement.
- [ ] Private, link-local, and Tailscale-only auxiliary listeners are not reported as public exposure.
- [ ] Unexpected wildcard or globally routable listeners fail verification.
- [ ] Unit tests cover IPv4, IPv6, wildcard, private, and loopback cases.
