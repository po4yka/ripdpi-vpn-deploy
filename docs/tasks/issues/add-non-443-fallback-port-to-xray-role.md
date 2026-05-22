---
title: Add non-443 fallback port to xray role for TLS-policing-home-ISPs bypass
type: task
status: backlog
area: xray-config
priority: high
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[tls-policing-home-isps]]"
linked_task: ../../../../RIPDPI/docs/tasks/issues/enforce-per-exit-ip-concurrent-tls-cap.md
---

- [ ] #task Add non-443 fallback port to xray role #repo/RIPDPI-VPN-DEPLOY #area/xray-config #status/backlog ⏫

## Motivation

50+ RU home-ISP ASNs apply TLS-handshake-level connection-count blocking on port 443 specifically. The confirmed primary workaround is to move VLESS+Reality+Vision off port 443. Currently the `xray` role only configures port 443 as the inbound; adding a non-443 fallback (e.g., 8443 or operator-configurable) lets the RIPDPI client fall through to it when the concurrent-TLS-cap is hit.

## Proposed change

Extend the `xray` Ansible role:

1. Add a configurable `xray_fallback_port` variable (default `8443`) to `ansible/roles/xray/defaults/main.yml`.
2. Add a second VLESS+Reality+Vision inbound bound to `xray_fallback_port` in the Xray config template.
3. Update nftables / firewall rules to permit the new port.
4. Update `emit-singbox.sh` / subscription generator to include the fallback endpoint in client profiles.
5. Document the fallback in `docs/CLIENT-NOTES.md` and `ansible/roles/xray/CLAUDE.md`.

## Canonical recipe

Extension of existing role — does not strictly fit "new role" but adheres to its spirit. Update the role's defaults + tasks + tests; add the configuration to operator-visible defaults. Closest documented recipe: §"New Ansible role" with most steps already in place; only need to add the new inbound + variable + secrets-coverage check + molecule scenario coverage.

### Linked client task

`linked_task:` points to the sibling RIPDPI Android task that consumes the fallback endpoint.

## Acceptance criteria

- [ ] `xray_fallback_port` variable configurable per cohort.
- [ ] Both port-443 and fallback-port inbounds active by default.
- [ ] Molecule scenario tests both inbounds reachable.
- [ ] Subscription generator includes the fallback endpoint.
- [ ] Documented in role's `CLAUDE.md` and `docs/CLIENT-NOTES.md`.

## Risks / open questions

- Operator firewall rules vary; default fallback port choice (8443) may conflict with other deployments.
- Fallback port may itself become a TSPU target over time — fallback port choice should be operator-configurable to allow rotation.

## References

- [[tls-policing-home-isps]] — wiki concept page
- Linked client task: `enforce-per-exit-ip-concurrent-tls-cap` in RIPDPI repo
