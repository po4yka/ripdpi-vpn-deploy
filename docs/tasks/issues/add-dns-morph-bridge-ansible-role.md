---
title: Add DNS-Morph bridge Ansible role
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
  - "[[dns-morph-bootstrap]]"
linked_task: ../../../../RIPDPI/docs/tasks/issues/spike-dns-morph-bootstrap-fallback-channel.md
---

- [ ] #task Add DNS-Morph bridge Ansible role #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔼

## Motivation

Companion to RIPDPI Android `spike-dns-morph-bootstrap-fallback-channel`. The DNS-Morph bootstrap protocol requires a bridge server reachable on standard DNS port 53/UDP that (a) processes handshake-shaped queries as DNS-Morph fragments and (b) forwards all other queries to a local standard DNS server for active-probing defense.

## Proposed change

New Ansible role `ansible/roles/dns-morph-bridge/` deploying:

1. The DNS-Morph reference daemon (or a re-implementation if the 2021 Tor pluggable-transport reference is too narrow for our deployment).
2. A local Unbound (or knot-resolver) for the active-probing-defense forwarder.
3. nftables rules permitting UDP/53 inbound.
4. Configuration template for the bridge's signing key and the upstream data-plane transport endpoint (typically VLESS+Reality on a separate port).

## Canonical recipe

new-role — follows §"New Ansible role" recipe verbatim:
1. Scaffold `ansible/roles/dns-morph-bridge/` (tasks, defaults, meta, handlers).
2. Add enable toggle to `ansible/group_vars/all.yml` (default disabled until linked client task ships).
3. Add secrets keys to `secrets/prod.secrets.example.yaml` (bridge signing key).
4. Molecule scenario under `ansible/roles/dns-morph-bridge/molecule/`.
5. `ansible/roles/dns-morph-bridge/CLAUDE.md`.
6. Update `README.md` for the new transport tier.
7. Wire into `ansible/site.yml` behind the toggle.

### Linked client task

`linked_task:` points to the sibling RIPDPI Android spike. Both must ship together.

## Acceptance criteria

- [ ] Role deploys cleanly to a fresh foreign VPS.
- [ ] `dig @<bridge-ip> www.example.com` returns a normal A record (active-probing defense).
- [ ] DNS-Morph encoded query produces a handshake response (smoke test).
- [ ] Molecule scenario passes.
- [ ] Documented in `docs/PROVIDER-NOTES.md` as a P4 fallback tier.

## Risks / open questions

- Reference code is 2021 Tor pluggable transport — re-implementing for Russia context may require non-trivial rework.
- UDP/53 inbound on a foreign VPS is operationally noisy (many scanners); rate-limiting strategy needed.
- Resolver routing: RU "trusted DNS" mandates may route client queries away from the bridge.

## References

- [[dns-morph-bootstrap]] — wiki concept page
- [[censorship-update-net4people-2026-05-22]] — net4people #619 source
- Linked client task: `spike-dns-morph-bootstrap-fallback-channel` in RIPDPI repo
