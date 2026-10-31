# Change: Encrypt node-side destination DNS resolution

Task ID: `SEC-1793428979810694`

## Why

Traffic-privacy audit item 8: every recipient destination was resolved on the node as plaintext UDP/53 to the pinned public resolvers, and the host's own lookups (apt, time sync, probes) used the provider's DHCP resolvers in clear, so an observer on the VPS uplink saw a per-destination log.

The recipient path was closed by `SEC-1793428673775693` (merged as `fix(security)!: resolve recipient names over DoH and watch borrowed identities`): the direct private Xray gateway hosts a loopback DNS forwarder on `127.0.0.2:53`, the normalizer's sealed resolver and the Xray frontend point at it, and the gateway answers over `https+local://` with `unexpectedIPs`. That change explicitly left the host resolver out of scope. This change closes the remaining host-side gap and records the DNS-Morph interaction. A first iteration of this change carried an alternative recipient forwarder (owned NAT redirect to an unprivileged gateway port); it was dropped on merge in favour of the already merged design.

## What Changes

- The host, when it runs systemd-resolved, gets a `resolved.conf.d` drop-in with explicit `DNS=` servers carrying certificate names, `Domains=~.`, `DNSOverTLS=yes`, `LLMNR=no` and `MulticastDNS=no`. Baseline restarts resolved through its existing transition task, proves one lookup, and withdraws the drop-in, restarts and fails if the lookup cannot succeed. **BREAKING** for a host whose uplink blocks TCP/853 to the pinned resolvers: baseline refuses instead of falling back to plaintext.
- Strict `firewall_egress_policy` admits TCP/853 as host infrastructure egress.
- The DNS-Morph interaction is unchanged: no new port-53 listener, stub release and deferred restoration keep their tasks. Under DNS-Morph the host resolver file bypasses resolved, so host lookups there stay plaintext to the pinned servers (documented residual).

## Capabilities

### New Capabilities

- `network/encrypted-destination-resolution`: host lookups use strict DNS over TLS with a fail-closed proof, and the DNS-Morph port-53 ownership is preserved.

### Modified Capabilities

- None.

## Impact

- **Ansible:** `baseline` (`resolver.yml` drop-in with fail-closed proof and notes), `firewall` (strict egress 853).
- **Contracts:** the firewall snapshot golden, resolver round-trip and firewall unit tests, `ansible/CLAUDE.md` DNS-Morph note.
- **Not changed:** Terraform, cloud-init, secrets schema, the transport-egress generation, client bundles, AmneziaWG device tunnels (their DNS is the device's own resolver choice), the DNS-Morph listener and its stub lifecycle. Existing nodes need a deploy for the drop-in to apply.
