# ANS-1794231660855533: Route family transport egress through the split-hop exit node

## Objective

With `vpn.split_hop_family_egress` on a split-hop Node A, every Xray, Hysteria and AmneziaWG recipient flow leaves through the B-initiated tunnel, IPv4 only, and fails closed while the tunnel is down. The default research scope keeps its behavior apart from the reverse-path and MSS repairs.

## Ownership

Single serialized lane. Ansible: `roles/split-hop-ingress/` (policy, configuration, enable tasks, defaults, notes), `roles/firewall/` (template, main tasks, defaults, notes), `roles/transport-egress/templates/gateway.json.j2`, `playbooks/site.yml`, `group_vars/all.yml`. Docs: decision 0003 and the split-hop pilot guide. Tests: `tests/unit/test_split_hop_native.py`, `tests/unit/test_split_hop_family_egress.py`, `tests/unit/test_transport_audit_network.py`, `tests/unit/test_transport_egress_role.py`, split-hop-ingress snapshot goldens.

## Execution

- [x] ANS-1794232229453495 Route family recipient UIDs and AWG originals through the tunnel with fail-closed guards in the split-hop policy #feature !high @item:ANS-1794231660855533
- [x] ANS-1794232364807121 Move AWG forwarding and NAT onto the tunnel and extend the shared firewall guard in family scope #feature !high @item:ANS-1794231660855533
- [x] ANS-1794232503959033 Keep the family direct gateway on IPv4 and refuse unsafe family combinations in site.yml #feature !high @item:ANS-1794231660855533
- [x] ANS-1794232643548719 Add native and unit regressions, refresh goldens, update ADR, role notes and pilot guide #feature !high @item:ANS-1794231660855533

## Verification

- Local narrow checks: the four test modules above, `make snapshot-check`, ansible-lint on the touched roles and `site.yml`; the new native family test runs in a namespace copy with a veth tunnel locally because this container has no WireGuard kernel module.
- Local gate: `make check`.
- Remote: PR CI on the exact head SHA, including the native lane that runs the WireGuard family test.
- Dry-run, staging, live and client: deferred to a separately authorized Node A/Node B dry-run and staging converge; this change does not run them.
- [x] ANS-1794550099725815 Keep the MSS clamp out of POSTROUTING so the transport-egress kernel audit admits the split-hop boundary #bug !high @item:ANS-1794231660855533
