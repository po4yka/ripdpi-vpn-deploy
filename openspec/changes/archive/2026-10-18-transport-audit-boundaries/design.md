## Context

The audit identified cross-role packet paths and admission gaps. Runtime versions stay pinned.

## Goals / Non-Goals

- Goal: Repair the confirmed code, configuration and operator-documentation errors with regression proof.
- Non-goal: Add protocol features, perform a dependency migration, modify a peer client repository or deploy.

## Decisions

- Local-destination and public-ingress predicates isolate hopping NAT from forwarded traffic.
- Split-hop retains a direct-egress guard independently of tunnel routes; explicit role retirement removes only owned state. Canonical firewall guards follow the effective role selector; standalone retirement refuses while a shared guard remains, so callers first converge the disabled canonical policy.
- IPv4 interface checks run in POSTROUTING, where the final marked route is visible. OUTPUT can retain the pre-mark interface and must not use it for this decision. The IPv6 original-traffic refusal remains in OUTPUT. Both owned and canonical guards follow this rule.
- Strict overlay allowances are bounded by enabled role and required protocol identity or destination.
- Official sing-box integer Mbps hints are rounded up from admitted exact server rates and reversed into client directions. Server negotiation clamps exact rates. RIPDPI currently cannot apply these hints; its supported bundles remain compatible and documentation states this limit. No aggregate server limiter is claimed.
- AWG rejects noncanonical legacy header values and equal handshake sizes rather than changing exported fingerprints.
- DNS-Morph accepts the existing 32-byte seed format. A separate explicit test selector permits echo-only; controller preflight precedes site and standalone mutations.
- WARP retains the checksum of upstream armored bytes and uses an ASCII keyring path.

## Contracts and ownership

Ansible owns runtime policy. Terraform public listener ownership is unchanged. Root owns shared integration and planning; the execution file assigns all parallel paths.

## Risks / Trade-offs

- Strict validation can reject formerly admitted invalid inputs; tests cover canonical existing profiles.
- Split-hop must preserve ingress replies and tunnel-independent denial; native Linux tests cover stop and restart.
- Negotiated hints are per connection and require supported clients; docs do not claim a security bandwidth ceiling.
- Synthetic tests cannot accept live WARP, NAT traversal or physical-device behavior.

## Migration Plan

Merge only after source gates, native hosted checks and review pass. Existing optional roles stay opt-in. The next separately authorized convergence applies policy. Roll back source with a reviewed revert; no secret rotation or provider mutation occurs here.
