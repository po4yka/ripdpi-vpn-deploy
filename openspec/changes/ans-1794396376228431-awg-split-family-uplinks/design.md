# Design: AWG with separate IPv4 and IPv6 uplinks

## Context

`scripts/awg_uplink.py` admits AWG only when `ip route get` for both families leaves through one interface with a public source, plus an IPv6 default route whose RA owner is unambiguous. The firewall template derives one `awg_forward_interface` (uplink, or the split-hop tunnel in family scope) and uses it for the forward-chain interface pin, the new-connection accept and the NAT masquerade. On UpCloud the IPv6 default route is on a second public NIC.

## Decisions

- Explicit opt-in. The IPv6 uplink is a named variable, never taken from `ansible_facts.default_ipv6`: a fact-derived interface could be an overlay (for example `tailscale0`) and silently move AWG egress off the provider uplink. Empty means "same as IPv4", which keeps every existing host unchanged.
- Per-family pinning in the same rules. In split mode each forward drop and the accept carry `meta nfproto ipv4|ipv6` with that family's uplink,; the `inet` forward hook sees only IPv4 and IPv6, so no other family needs a rule. All drops stay before `established,related`. Uplink names may not be `lo`, the split-hop tunnel or an AWG instance.
- NAT keeps the IPv4 comment `awg-nat-<instance>` and adds `awg-nat-v6-<instance>` only in split mode, so consumers that count the IPv4 rule (the real-VPS evidence lane) are unaffected.
- Equal values collapse to the old template branch, proven by unchanged snapshots and a render-equality test.
- Split-hop family scope already forwards both families to the tunnel (and rejects forwarded IPv6), so the IPv6 uplink does not apply there.

## Alternatives rejected

- Infer the IPv6 uplink from facts: rejected for the overlay risk above.
- Bridge or bond the provider NICs: provider networking is outside the role's authority.
- Keep AWG off on UpCloud: production and staging split-hop Node A run on UpCloud.

## Rollback

Unset `firewall_awg_uplink6_interface`; hosts that never set it render the previous ruleset.
