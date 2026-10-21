# iOS split routing: curated direct allowlist, fail-closed VPN default

**Evidence date:** 2026-07-14

**Scope:** repository-owned conclusions from physical tests of Shadowrocket,
Happ, and INCY. This document intentionally contains no external citations,
client credentials, private subscription URLs, cryptographic secrets, or
public network addresses.

## Decision

Use an allowlist policy. Unmatched traffic must use the selected VPN profile;
only local prefixes and entries in a pinned, repository-owned direct-domain
dataset may use `DIRECT`. Do not enable a broad address-classification rule in
the strict profile: shared hosting and distributed edges make address ownership
too coarse for a no-leak boundary.

Name profiles by their technical behavior:

- `direct-domain-strict` — local prefixes and the curated domain dataset are
  direct; every other destination uses VPN.
- `direct-address-compat` — adds an explicitly accepted address dataset for
  compatibility and carries the corresponding exposure warning.

The existing `scripts/emit-singbox.sh` output is not this iOS policy. It sends
unmatched traffic and its remote resolver through the selected outbound, while
its application exceptions are Android-specific. Any iOS routing artifact must
therefore be a separate repository-owned generator with schema and snapshots.

## Classification contract

The strict policy consumes a pinned local tag named
`geosite:curated-direct`. Its source revision, digest, recursive includes, IDN
normalization, deduplication, license, and empty-output rejection must be stored
and tested in this repository. A remotely mutable category is not an accepted
runtime dependency.

The compatibility profile may additionally consume
`geoip:curated-direct`, but it must remain a separate output. A missing direct
entry safely falls through to VPN; an overly broad direct entry exposes the
access-network address to the destination.

Local direct prefixes are limited to:

```text
10.0.0.0/8
100.64.0.0/10
127.0.0.0/8
169.254.0.0/16
172.16.0.0/12
192.168.0.0/16
224.0.0.0/4
255.255.255.255/32
::1/128
fc00::/7
fe80::/10
ff00::/8
```

There is no blanket direct IPv6 route. Unmatched IPv4 and IPv6 both use VPN.

## Resolver contract

Use two independently configured resolvers and bind each to its route:

- the remote resolver uses the selected VPN outbound;
- the direct resolver is used only for a direct-domain match;
- ambiguous application-owned encrypted DNS falls through to VPN;
- a resolver observed behind the VPN exit is not an access-network DNS leak,
  but it is not proof that route-bound split DNS worked.

The generator must accept resolver endpoints as validated operator input; this
document does not embed provider names or remotely hosted configuration URLs.
The rendered profile must keep `IPIfNonMatch` semantics so a domain rule is
checked before address rules.

## Client-specific contract

### Happ

The accepted shape uses `GlobalProxy=true`,
`RouteOrder=block-direct-proxy`, `DomainStrategy=IPIfNonMatch`, a local pinned
geodata artifact, separate direct and remote resolvers, and `FakeDNS=true`.
`GlobalProxy=true` is load-bearing: an unmatched destination must not become
direct. `UseChunkFiles=true` is retained for the physically accepted iOS
configuration.

### INCY

Use the same fail-closed categories but retain the field types expected by the
installed build. The accepted test configuration used `FakeDNS=false`. First
rollout must use a local payload; URL-backed autorouting is not allowed until
integrity, rollback, and failure behavior are repository-tested.

### Shadowrocket

The physically accepted rule order is:

```ini
[Rule]
# compiled exact and suffix entries from geosite:curated-direct
IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
IP-CIDR,100.64.0.0/10,DIRECT,no-resolve
IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
IP-CIDR,169.254.0.0/16,DIRECT,no-resolve
IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
IP-CIDR6,::1/128,DIRECT,no-resolve
IP-CIDR6,fc00::/7,DIRECT,no-resolve
IP-CIDR6,fe80::/10,DIRECT,no-resolve
FINAL,PROXY
```

This is an empirical, version-pinned contract. The repository generator must
compile source-format includes into exact and suffix rules rather than passing
source files through as client rule sets.

## Physical acceptance matrix

The strict profile was activated in all three applications on a physical iOS
device. Network addresses remain redacted by policy.

| Client | VPN transport | Unmatched IPv4 | Curated-domain IPv4 | IPv6 | Resolver observation | Result |
|---|---|---|---|---|---|---|
| Shadowrocket | P0 REALITY | `<redacted-address>` via VPN | `<redacted-address>` direct | `<redacted-address>` via VPN | public resolvers behind VPN; access-network resolver absent | PASS |
| Happ | P0 REALITY | `<redacted-address>` via VPN | `<redacted-address>` direct | explicit failure, no native leak | mixed public resolvers; access-network resolver absent | PASS with resolver warning |
| INCY | P2 Hysteria2 | `<redacted-address>` via VPN | `<redacted-address>` direct | `<redacted-address>` via VPN | public and exit-side resolvers; access-network resolver absent | PASS |

Run the following matrix after every client, generator, or geodata change:

| Case | Expected path | Required evidence |
|---|---|---|
| Curated direct-domain entry | DIRECT | client log identifies the direct rule |
| Unmatched public destination | VPN | observed address matches the selected exit |
| Public destination on a shared edge | VPN in strict mode | no broad address rule overrides the final action |
| Literal local address | DIRECT | local service works without server traffic |
| Unmatched IPv6 destination | VPN or explicit failure | native access-network IPv6 is never reported |
| Direct-domain lookup | direct resolver | client log or controlled telemetry identifies the route |
| Unmatched-domain lookup | remote resolver through VPN | telemetry identifies the selected outbound |
| Dataset refresh unavailable | existing policy remains active | no empty allowlist, global-direct fallback, or tunnel loss |

A green connection indicator is insufficient. Record only redacted route,
matched-rule, resolver-path, address-family, client-version, and dataset-digest
evidence.

## Required repository work

1. Add tracked strict and compatibility policy inputs with technical names.
2. Add schema and snapshot tests for Happ/INCY JSON, deep-link encoding,
   Shadowrocket ordering, the fail-closed final action, and IPv6 coverage.
3. Vendor or reproducibly materialize the pinned direct-domain dataset and
   retain its revision, digest, include graph, and license in-repository.
4. Add a repeatable physical-device runner that emits only redacted evidence.
5. Keep resolver filtering separate from routing so each control can be tested
   and rolled back independently.
