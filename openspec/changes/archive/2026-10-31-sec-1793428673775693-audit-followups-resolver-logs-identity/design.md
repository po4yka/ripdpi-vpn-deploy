## Context

`SEC-1793386547449444` closed the audit's retention and fleet-fingerprint findings and listed items 7 to 13 as non-goals. This change closes them: node-side DNS privacy (8), decoy log identity (9), REALITY target drift (10), the WireGuard-shaped AmneziaWG guard (7), dual-stack REALITY listeners (13) and two documented decisions (11, 12).

## Goals / Non-Goals

- Goal: no plaintext recipient name leaves the node on a default profile; decoy logs carry no visitor identity; the watchdog notices a drifted REALITY target; production cannot ship an unmeasured WireGuard-shaped instance.
- Non-goal: host-wide DNS-over-TLS for the operating system resolver (apt, time sync, geodata), which would need `systemd-resolved` on every image and a TCP/853 egress rule; per-device uTLS or bandwidth variation; automatic REALITY target failover.

## Decisions

- The DoH forwarder lives in the direct gateway, the one Xray process that always exists when the normalizer exists and whose egress is already policy-bounded. glibc has no resolver port option, so the forwarder binds port 53 and the direct unit gains `CAP_NET_BIND_SERVICE`; the WARP gateway and normalizer stay capability-free. Rejected: a DoH client inside the Python normalizer (new TLS and DNS wire code), `systemd-resolved` DoT (absent on the Debian image, strict mode becomes a single point of failure, needs a firewall change), an nft output redirect to an unprivileged port (NAT in the kernel-policy contract).
- `127.0.0.2` is `LOCAL_DNS_FORWARDER` in `transport_destination_policy.py`, the one loopback resolver the normalizer validator admits; templates test membership of that literal and a rendering test ties it to the constant.
- `nonIPQuery: reject` (the pinned release's default) answers non-A/AAAA queries at once instead of forwarding them to the dokodemo target in plaintext; `https+local://` with IP URLs needs no bootstrap resolution and bypasses gateway routing. The kernel reply rule is scoped to source `127.0.0.2`, port 53 and conntrack reply direction so every other loopback destination stays denied.
- DNS-Morph binds UDP/53 on every address, which conflicts with the specific bind, so that profile keeps the numeric upstream pair; the WARP namespace keeps it because the vendor client must resolve its control plane before a tunnel exists.
- The Xray frontend's DNS points at the forwarder too: outside cascade it is unused for recipient traffic, and a frontend-side lookup now fails closed instead of leaving in plaintext.
- nginx `log_format` replaces `$remote_addr` and the user agent with `-` and keeps `$status` as field nine for the watchdog's `awk` counter.
- The watchdog probe is a Python heredoc in the existing script: `ssl.create_default_context`, TLS 1.3 minimum, ALPN `h2`, `set_ecdh_curve("X25519")` where the binding allows it, certificate verification for the first server name. Loopback targets are the owned self-steal site, already probed through nginx.
- The AmneziaWG guard keys on inventory `env == 'prod'` like the decoy-site gate and reads `awg_wireguard_shaped_measurement` from the same private override file; it matches the shape from the effective instance list after transport semantics, so defaults and profile inputs are both covered.

## Contracts and ownership

- Scripts: `transport_destination_policy.py` (constant), `transport_egress_config.py` (resolver selection), `transport_egress_normalizer.py` (validator), `transport_egress_kernel.py` (reply rule).
- Ansible: `transport-egress/templates/{gateway.json.j2,gateway.service.j2}`, `warp-outbound/templates/resolv.conf.j2`, `xray/templates/config.json.j2`, `nginx-xhttp/templates/site.conf.j2`, `reality-self-steal/templates/site.conf.j2`, `watchdog/templates/{vpn-watchdog.env.j2,vpn-watchdog.sh.j2}`, `amneziawg/tasks/{enable.yml,guard-wireguard-shape.yml}`, `group_vars/all.yml`.
- Fixtures: snapshot goldens for the touched templates. Native lab fixtures override the resolver to their own UDP stub and write their own gateway configuration, so they are unchanged.

## Risks / Trade-offs

- A failing DoH path stalls normalizer lookups (1 s timeout, one attempt) instead of leaking → acceptable; both upstreams are tried by Xray's built-in DNS.
- The direct gateway can bind any privileged loopback port → bounded by `CapabilityBoundingSet`, the host input firewall and the gateway's deny-listed destinations.
- Native CI lanes that build the topology without a forwarder (classifier boundary) → they resolve nothing by name or override the resolver; the pull request's native run is the check.
- Existing production hosts with a WireGuard-shaped instance fail the next deploy → the fail message names the variable and the documentation explains the measurement record.

## Migration Plan

Forward: ordinary deploy; the egress generation republishes with the forwarder and the new unit capability. Production hosts carrying a WireGuard-shaped AmneziaWG instance set `awg_wireguard_shaped_measurement` in their private override file first. Rollback: revert the commit; the egress transaction restores the previous generation and unit bytes.
