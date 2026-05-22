---
title: Add Hysteria Realm rendezvous role
type: task
status: backlog
area: ansible
priority: medium
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[hysteria2-tuic]]"
linked_task: ../../../../RIPDPI/docs/tasks/issues/wire-hysteria-realm-stun-nat-traversal.md
---

- [ ] #task Add Hysteria Realm rendezvous role #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔼

## Motivation

Companion to RIPDPI Android `wire-hysteria-realm-stun-nat-traversal`. The Hysteria Realm protocol (sing-box v1.14.0-alpha.22, 2026-05-11) requires a rendezvous service that mediates endpoint exchange between two peers, then drops out of the data path once UDP hole-punching completes.

Per upstream release notes, asymmetric deployment (one peer running sing-box Realm, the other running mainline `apernet/hysteria` server) is NOT yet supported. Both peers must run sing-box ≥ alpha.22 — implying the rendezvous server is also a sing-box instance in realm-service mode, not a generic Hysteria2 server.

## Proposed change

New Ansible role `ansible/roles/hysteria-realm/` deploying:

1. sing-box ≥ v1.14.0-alpha.22 (pinned upstream tag) configured as a realm rendezvous service.
2. TLS-wrapped rendezvous channel (the realm flow is small, so wrap behind any TLS or HTTPS server for ASN-blocklist resistance).
3. nftables rules for the realm rendezvous port (TBD; consult sing-box upstream).
4. Operational toggles in `group_vars/all.yml` (default disabled until linked client task ships).

## Canonical recipe

new-role — follows §"New Ansible role" recipe verbatim.

### Linked client task

`linked_task:` points to the sibling RIPDPI Android task. Both must ship together.

## Acceptance criteria

- [ ] Role deploys sing-box realm service to a fresh foreign VPS.
- [ ] Two test clients (sing-box CLI or RIPDPI dev build) successfully register endpoints and exchange via rendezvous.
- [ ] Molecule scenario passes.
- [ ] `docs/PROVIDER-NOTES.md` updated with realm-tier deployment notes.
- [ ] sing-box version pin and upgrade procedure documented in role's `CLAUDE.md`.

## Risks / open questions

- sing-box v1.14.0 is still alpha — production deployment requires explicit risk acceptance or pinning to a stable mid-tier release once available.
- Rendezvous channel reachability from RU clients is the only fixed-server dependency — if RU TSPU classifies the rendezvous TLS handshake as VPN-shaped, the bypass fails at the rendezvous step (not the hole-punch).

## References

- [[hysteria2-tuic#Hysteria Realm NAT-Traversal (sing-box v1.14.0-alpha.22, 2026-05-11)]]
- [[censorship-update-github-releases-2026-05-22]]
- Linked client task: `wire-hysteria-realm-stun-nat-traversal` in RIPDPI repo
