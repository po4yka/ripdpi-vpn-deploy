# Change: Encrypt node-side destination DNS resolution

Task ID: `SEC-1793428979810694`

## Why

Traffic-privacy audit item 8: every recipient destination is resolved on the node, and that resolution leaves the VPS uplink as plaintext UDP/53 to `1.1.1.1` and `8.8.8.8`. An observer on the uplink therefore sees a per-destination log of every domain that every device visits, which defeats the purpose of the encrypted transports in front of it.

Three places produce or pin that plaintext path today:

- The transport-egress normalizer resolves each sniffed or client-supplied domain through sealed libc/NSS. `scripts/transport_egress_config.py` pins the public resolver pair into the normalizer's `resolv.conf`, and the owned kernel policy admits exactly that port-53 traffic. This is the per-destination leak.
- The private Xray gateways render the same pair as plain port-53 `dns.servers` (with `unexpectedIPs`), and the Xray frontend's own `dns` block uses the same pair.
- The host keeps systemd-resolved on the provider's DHCP resolvers with no `DNSOverTLS=` drop-in, so apt, time sync, probes and other host lookups are plaintext too.

glibc's `dns` NSS module cannot speak DNS over TLS or HTTPS, so the normalizer's resolver cannot "stay" as it is if the goal is met.

## What Changes

- The normalizer keeps sealed libc/NSS, but its sealed `resolv.conf` names only the loopback address, and the owned kernel policy redirects the normalizer's port-53 traffic to a DNS forwarder inbound on the direct private Xray gateway. That gateway answers A/AAAA from Xray's built-in DNS over `https+local://` (DoH) to the pinned public resolvers, keeps `unexpectedIPs` on every upstream, and drops every other query type. No plaintext DNS leaves the node for recipient destinations.
- The kernel policy gains an owned output NAT chain for that redirect and the matching admission, normalizer and gateway reply rules. The forwarder port is part of the policy projection, port reservation and owner admission.
- Both private gateways and the non-cascade Xray frontend render DoH `dns.servers`. The cascade branch keeps `tcp://` servers because its queries already traverse the classifier tunnel.
- The host, when it runs systemd-resolved, gets a `resolved.conf.d` drop-in with explicit `DNS=` servers, `Domains=~.`, `DNSOverTLS=yes`, `LLMNR=no` and `MulticastDNS=no`. Baseline proves one encrypted lookup after the restart and withdraws the drop-in, restarts and fails if the lookup cannot succeed. **BREAKING** for a host whose uplink blocks TCP/853 to the pinned resolvers: baseline refuses instead of falling back to plaintext.
- Strict `firewall_egress_policy` admits TCP/853 as host infrastructure egress.
- The DNS-Morph interaction is unchanged: no new port-53 listener is bound, stub release and deferred restoration keep their existing tasks, and the DNS-Morph profile keeps bypassing resolved for host lookups (documented residual).

## Capabilities

### New Capabilities

- `network/encrypted-destination-resolution`: recipient destination names and host lookups are resolved without plaintext DNS on the uplink, with the anti-rebinding filter, the literal-only gateway contract and the DNS-Morph port-53 ownership preserved.

### Modified Capabilities

- None.

## Impact

- **Scripts:** `transport_egress_config.py` (forwarder port and loopback nameserver), `transport_egress_normalizer.py` (admits the exact loopback forwarder as the sealed nameserver), `transport_egress_kernel.py` (optional `resolver.forwarder_port`, NAT redirect, admission and reply rules, port intervals).
- **Ansible:** `transport-egress` (`gateway.json.j2`, DoH upstream default), `xray` (`config.json.j2` DoH strings), `baseline` (`resolver.yml` drop-in with fail-closed proof), `firewall` (strict egress 853).
- **Contracts:** the egress policy projection gains an optional key; snapshot goldens, unit tests and the native egress fixtures that apply the production kernel projection; `docs/reference/transport-egress.md` and the role notes.
- **Not changed:** Terraform, cloud-init, secrets schema, client bundles, AmneziaWG device tunnels (their DNS is the device's own resolver choice), the DNS-Morph listener and its stub lifecycle. Existing nodes need a deploy for the runtime change.
