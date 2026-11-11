# Change: Let AmneziaWG use separate IPv4 and IPv6 uplinks

Task ID: `ANS-1794396376228431`

## Why

AmneziaWG admission and its nftables forward and NAT rules assume one public uplink carries both IPv4 and IPv6. UpCloud attaches IPv6 to a separate interface (IPv4 default route on `eth0`, IPv6 default route on `eth1`), so `scripts/awg_uplink.py` refuses with `awg-dualstack-uplink-unavailable` and no UpCloud node can run AWG. Observed on the staging Node A dry-run for `ANS-1794231660855533`; the UpCloud CI profile keeps AWG off for the same reason.

## What Changes

- New firewall variable `firewall_awg_uplink6_interface` (default empty): the exact IPv6 AWG uplink. It is never inferred from facts; empty keeps IPv6 on the IPv4 uplink.
- `scripts/awg_uplink.py --interface6` admits the IPv6 route, default route and RA ownership on that interface; IPv4 stays on `--interface`.
- `firewall/tasks/awg-uplink.yml` validates both names (not `lo`, the split-hop tunnel or an AWG instance) and passes both to the checker, in the firewall and the amneziawg import contexts.
- `nftables.conf.j2`: when the IPv6 uplink differs, AWG forward drops, the new-connection accept and the inet NAT masquerade rules pin `meta nfproto ipv4` to the IPv4 uplink and `ipv6` to the IPv6 uplink; the IPv6 NAT rules use `awg-nat-v6-<instance>` comments. Equal or empty values render the previous ruleset byte for byte. Split-hop family scope keeps both families on the tunnel.

## Capabilities

### New Capabilities

- `network/awg-split-family-uplinks`: AWG forwarding and NAT on providers with separate IPv4 and IPv6 interfaces.

### Modified Capabilities

- None.

## Impact

- Ansible: firewall role defaults, AWG uplink task and nftables template; role notes for firewall and amneziawg.
- Scripts: `awg_uplink.py`, the secrets-coverage allowlist.
- Tests: checker and render tests; snapshots unchanged.
- Operators of UpCloud AWG nodes set `firewall_awg_uplink6_interface` through the limited extra-vars file or a reviewed profile. No Terraform, secrets schema or client contract change.
