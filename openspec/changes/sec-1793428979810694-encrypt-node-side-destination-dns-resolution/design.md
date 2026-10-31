## Context

See proposal.md. The normalizer (`scripts/transport_egress_normalizer.py`) runs with `RestrictAddressFamilies=AF_INET AF_INET6`, no capabilities, `hosts: dns` NSS and a sealed `resolv.conf` whose content it verifies against its config at start. It resolves every domain to literals and hands only admitted literals to the private Xray gateways, so the gateways' `dns` blocks are never consulted today. The owned kernel policy (`scripts/transport_egress_kernel.py`) admits normalizer-UID traffic only to the backends and to the pinned nameservers on port 53. DNS-Morph binds `0.0.0.0:53` UDP, so baseline releases the resolved stub while the bridge is enabled; `systemd-resolved` is optional on supported images (baseline imports `resolver.yml` only when the service exists).

Xray 26.3.27 (the pinned runtime) was exercised locally: a `dokodemo-door` inbound routed to a `dns` outbound answers UDP and TCP A/AAAA from the built-in DNS, `unexpectedIPs` removes loopback and private answers from a mixed response and leaves an all-denied name with an empty answer, `nonIPQuery: drop` leaves a TXT query unanswered, and the `https+local://` object form with `unexpectedIPs` passes `xray run -test`.

## Goals / Non-Goals

- Goal: no per-destination DNS query leaves the VPS uplink in clear for recipient traffic (P0 REALITY, P1 XHTTP, P2 Hysteria).
- Goal: host lookups use strict DoT when resolved is present, without breaking a deploy silently.
- Goal: keep the literal-only gateway contract, the normalizer's own candidate policy, the `unexpectedIPs` filter and the DNS-Morph stub lifecycle unchanged.
- Non-goal: AmneziaWG device tunnels; their DNS is the device resolver configuration and leaves the node through NAT as the device sends it.
- Non-goal: the WARP namespace resolver (`warp-outbound`), the cascade classifier's DNS path, or any change to the DNS-Morph bridge or its Unbound recursor.
- Non-goal: changing the pinned resolver vendors or making them an operator secret.

## Decisions

- **Loopback forwarder inside the egress generation, not systemd-resolved.** The normalizer keeps glibc and a sealed `resolv.conf` of `nameserver 127.0.0.1`. glibc cannot name a port, so the owned table gains `type nat hook output priority -100` rules that redirect normalizer-UID `udp`/`tcp` dport 53 on `127.0.0.1` to the direct gateway's forwarder port `12053`. The redirect precedes the admission (`-5`) and normalizer (`300`) filter hooks, which therefore see the forwarder port. Rejected: pointing the normalizer at the resolved stub `127.0.0.53`. The stub is disabled whenever DNS-Morph is enabled, resolved is absent on some supported images, resolved queries DHCP per-link servers in parallel unless `Domains=~.` is set, and glibc's single one-second attempt would couple recipient latency to a host daemon restart. Rejected: letting the gateway resolve domains itself. That reverses the "only admitted literals reach native gateways" contract and the normalizer's happy-eyeballs and UDP rebinding checks. Rejected: a DoH client inside the resolver worker. It adds a DNS wire-format parser to a sealed security boundary for no gain over Xray's existing one.
- **Forwarder is only on the direct gateway.** The normalizer resolves in the host namespace for both backends; the WARP gateway runs inside its namespace and keeps only the DoH `dns.servers` change.
- **`127.0.0.1` is the only loopback nameserver the normalizer admits.** `validate_config` keeps refusing every other loopback or private nameserver (the existing `127.0.0.53` regression stays). The kernel validator admits a loopback nameserver only together with `forwarder_port`, and requires exactly `['127.0.0.1']` when the port is present. A projection without the port keeps today's direct port-53 rules; the native fixtures use that form with an authoritative peer resolver.
- **DoH, not DoT, for the gateway.** `https+local://` dials directly as the gateway UID on TCP/443, which the gateway's destination chain already admits for public addresses and which blends with the node's other HTTPS egress; TLS roots come from the host `ca-certificates` bundle readable under `ProtectSystem=strict`. The upstream list is a role default (`transport_egress_dns_upstreams`) because the normalizer and kernel policy no longer need the upstream addresses; the forwarder port stays in `transport_egress_config.py` next to the other fixed ports and in `intervals()` for reservation and owner admission.
- **Host drop-in is strict with a proof and compensation.** `DNS=1.1.1.1#cloudflare-dns.com 8.8.8.8#dns.google`, `Domains=~.` (so resolved routes every name to the global servers instead of racing DHCP per-link servers), `DNSOverTLS=yes`, `LLMNR=no`, `MulticastDNS=no`. The existing restart task also fires when the drop-in changes; the deferral clause that protects stub restoration keeps its scope. After a changed restart, `resolvectl query` proves one lookup; the rescue removes the drop-in, restarts and fails with `encrypted-resolver-unavailable`. Rejected: `DNSOverTLS=opportunistic` (downgradable by an active adversary, which is the threat model). Rejected: installing resolved where it is absent (host resolver takeover outside this change's evidence).
- **Frontend DoH strings only outside cascade.** The non-cascade frontend never consults its DNS today (`domainStrategy: AsIs`, SOCKS outbound carries domains), so the change is hygiene and a safe default for future resolution. The cascade branch keeps `tcp://` because its DNS is routed through the classifier by inbound tag and the far end is a separate contract.

## Contracts and ownership

- `scripts/transport_egress_config.py`: `RESOLVER_FORWARDER_PORT = 12053`; normalizer `resolver.nameservers = ['127.0.0.1']`; policy `resolver = {nameservers, forwarder_port}`.
- `scripts/transport_egress_normalizer.py`: `validate_config` admits `127.0.0.1` as a nameserver; runtime sealing unchanged (it compares the rendered file to the config).
- `scripts/transport_egress_kernel.py`: `validate` accepts optional `resolver.forwarder_port`, adds it to the port collision set and to `intervals()`; `render` adds the `resolver_nat` chain, the admission drop, the normalizer accept and the gateway reply accepts when the port is present.
- `ansible/roles/transport-egress`: `defaults/main.yml` adds `transport_egress_dns_upstreams`; `templates/gateway.json.j2` renders DoH servers with `unexpectedIPs`, a `dns-forwarder` dokodemo inbound (direct gateway only), a `dns-resolver` outbound with `nonIPQuery: drop` and the routing rule; `CLAUDE.md` design note.
- `ansible/roles/xray/templates/config.json.j2`: non-cascade DoH strings.
- `ansible/roles/baseline/tasks/resolver.yml`: drop-in, restart condition, proof block; `CLAUDE.md` note.
- `ansible/roles/firewall/templates/nftables.conf.j2`: strict egress `tcp dport 853 accept`.
- Tests: `tests/unit/test_transport_egress_kernel.py`, `test_transport_destination_boundary.py`, `test_transport_egress_role.py`, `test_resolver_roundtrip.py`, `test_firewall_egress_policy.py`, `test_cascade_xray_integration.py`; snapshot goldens for `transport-egress`, `xray`, `firewall`; native egress fixtures keep applying the production projection (now with the NAT chain) in CI.
- Docs: `docs/reference/transport-egress.md` resolver paragraph and port list; `ansible/CLAUDE.md` DNS-Morph paragraph gains the residual host-path note.

## Risks / Trade-offs

- DoH upstream unreachable from a node → recipient resolution fails closed (`resolution-unavailable`), the same failure class as today when UDP/53 is filtered; no plaintext fallback by design. Mitigation: two independent upstream vendors.
- TCP/853 blocked for the host → baseline fails with the drop-in withdrawn and DNS restored. Mitigation: categorical failure before any later role; the operator can recreate the node elsewhere.
- One extra hop (normalizer → gateway → DoH) on cold names. Mitigation: Xray caches by TTL and reuses the HTTP/2 connection; glibc's `timeout:1 attempts:1` stays, and the normalizer's five-second lookup budget is unchanged.
- Owned DNAT is a new rule class in the egress table. The foreign-authority audit is unchanged (it ignores the owned table), the verify digest covers the new chain, and the native kernel and egress fixtures apply the rendered policy in CI.
- Under DNS-Morph the host's `/etc/resolv.conf` points at the upstream list, so host lookups there stay plaintext (now to the pinned global servers). Recipient traffic is still encrypted because the forwarder redirect does not depend on the stub.
- `LLMNR=no` and `MulticastDNS=no` turn off local-link name services on the host; no role depends on them.

## Migration Plan

- Forward: deploy renders the new generation (normalizer config, policy with NAT chain, gateway configs with forwarder) and the frontend config through the existing whole-route transaction; baseline writes the drop-in and restarts resolved before transport roles. No secrets or schema change.
- Rollback: the existing generation rollback restores the previous policy and configs; removing the drop-in and restarting resolved restores plaintext host DNS. The firewall change is additive.
- Gates: narrow unit tests, `make snapshot-check`, then `make check`; CI runs the native egress and kernel lanes that apply the production projection; dry-run, staging, live and client evidence stay with a separately authorized deploy.
