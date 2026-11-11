# ANS-1794396376228431: Let AmneziaWG use separate IPv4 and IPv6 uplinks

## Objective

AmneziaWG runs on providers that attach IPv6 to a separate interface, with admission, forwarding and NAT pinned per address family to an explicitly named IPv6 uplink; hosts without that setting keep the previous ruleset.

## Ownership

Single serialized lane. Ansible: `roles/firewall/defaults/main.yml`, `roles/firewall/tasks/awg-uplink.yml`, `roles/firewall/templates/nftables.conf.j2`, the firewall and amneziawg `CLAUDE.md` notes. Scripts: `scripts/awg_uplink.py`, `scripts/check-secrets-coverage.py`. Tests: `tests/unit/test_awg_dualstack.py`, `tests/unit/test_firewall_egress_policy.py`.

## Execution

- [x] ANS-1794397013800385 Admit and pin AWG forwarding and NAT to separate IPv4 and IPv6 uplinks #feature !high @item:ANS-1794396376228431

## Verification

- Local narrow checks: the AWG uplink and firewall render tests, `make snapshot-check`, `nft -c` on rendered rulesets, ansible-lint on the firewall and amneziawg roles, `scripts/check-secrets-coverage.py`.
- Independent security review of the patch.
- Read-only admission run on the UpCloud staging Node A of `ANS-1794231660855533`.
- Remote: PR CI on the exact head SHA, including the Linux native firewall and AWG tests.
- Staging: the staging Node A deploy with `firewall_awg_uplink6_interface: eth1`, recorded under `ANS-1794231660855533`.
