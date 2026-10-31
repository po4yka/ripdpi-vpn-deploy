## Context

See proposal.md. The recipient path already resolves through the direct gateway's loopback forwarder (`127.0.0.2:53`, DoH upstreams with `unexpectedIPs`) since `SEC-1793428673775693`; that design gives the direct gateway unit `CAP_NET_BIND_SERVICE` and falls back to plaintext upstreams under DNS-Morph, which binds UDP/53 on every address. The host resolver was left out of that change. `systemd-resolved` is optional on supported images: baseline imports `resolver.yml` only when the service exists, and DNS-Morph migrates the host symlink to the upstream list and releases the stub.

An earlier iteration of this change implemented the recipient forwarder differently (sealed `127.0.0.1`, an owned `nat` output redirect to an unprivileged gateway port, no capability, DNS-Morph independent). It was proven locally but dropped when the repository merged the other design first; replacing a merged security fix is a separate decision.

## Goals / Non-Goals

- Goal: host lookups use strict DoT when resolved is present, without breaking a deploy silently.
- Goal: keep the DNS-Morph stub lifecycle unchanged.
- Non-goal: the recipient forwarder, its capability or its DNS-Morph fallback (owned by the merged change).
- Non-goal: installing systemd-resolved where it is absent; AmneziaWG device DNS; the WARP namespace resolver.

## Decisions

- **Strict DoT with a proof and compensation.** `DNS=1.1.1.1#cloudflare-dns.com 8.8.8.8#dns.google`, `Domains=~.` (so resolved routes every name to the global servers instead of racing DHCP per-link servers), `DNSOverTLS=yes`, `LLMNR=no`, `MulticastDNS=no`. The existing restart task also fires when the drop-in changes; the deferral clause that protects stub restoration keeps its scope. After a changed restart, `resolvectl query` proves one lookup; the rescue removes the drop-in, restarts and fails with `encrypted-resolver-unavailable`. Rejected: `DNSOverTLS=opportunistic` (downgradable by an active adversary, which is the threat model). Rejected: installing resolved where it is absent (host resolver takeover outside this change's evidence).
- **TCP/853 in strict egress** next to the existing port-53 rules, because resolved's DoT would otherwise be dropped on hosts without transport-driven open egress.

## Contracts and ownership

- `ansible/roles/baseline/tasks/resolver.yml`: drop-in, restart condition, proof block; `CLAUDE.md` note.
- `ansible/roles/firewall/templates/nftables.conf.j2`: strict egress `tcp dport 853 accept`.
- Tests: `tests/unit/test_resolver_roundtrip.py`, `tests/unit/test_runtime_audit_regressions.py`, `tests/unit/test_firewall_egress_policy.py`; firewall snapshot golden.
- Docs: `ansible/CLAUDE.md` DNS-Morph paragraph.

## Risks / Trade-offs

- TCP/853 blocked for the host → baseline fails with the drop-in withdrawn and DNS restored. Mitigation: categorical failure before any later role; the operator can recreate the node elsewhere.
- Under DNS-Morph the host's `/etc/resolv.conf` points at the upstream list, so host lookups there stay plaintext (now to the pinned global servers).
- `LLMNR=no` and `MulticastDNS=no` turn off local-link name services on the host; no role depends on them.

## Migration Plan

- Forward: deploy writes the drop-in and restarts resolved before transport roles; the firewall change is additive. No secrets or schema change.
- Rollback: removing the drop-in and restarting resolved restores plaintext host DNS.
- Gates: resolver round-trip and firewall unit tests, `make snapshot-check`, `make check`; dry-run, staging, live and client evidence stay with a separately authorized deploy.
