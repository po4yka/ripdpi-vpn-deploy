# ADR: Split-hop relay topology against flow-level dual-role detection

Status: **Pilot** (2026-05). Implementation scaffold landed; flow-data
verification still operator-driven, pending two-VPS pilot stand.

## Motivation

A flow-level classifier observing per-IP behaviour over a window can
score whether an IP both **accepts inbound client connections** and
**initiates outbound upstream connections** within the same window.
The original FOCI 2026 publication (Almutairi, Harfoush, Viniotis,
NC State, 2026-02; <https://www.petsymposium.org/foci/2026/foci-2026-0008.pdf>)
reports 23% relay detection at 0.18% FPR against legitimate traffic
when using a per-IP **Relay Suspicion Score**: the fraction of flows
where the IP simultaneously acts in both roles.

The detection signal is **architectural**, not payload-shape. Every
payload-obfuscation transport in this repo (REALITY, XHTTP, Hysteria,
AmneziaWG) leaves the dual-role signature intact, because all of them
run ingress + egress on the same VPS IP. A flow observer at the
upstream's vantage cannot read the payload, but it can correlate
SYN-direction and per-flow byte counts.

This is a defensive measure against a *published* technique. We do not
have direct confirmation that any specific filtering pipeline currently
runs flow-level dual-role scoring at scale; the cost calculus on the
classifier side (backbone-scale flow records, per-IP windows) is non-
trivial, and the published 0.18% FPR means a deployment-scale operator
absorbs many false positives. The trade-off below evaluates the
mitigation against the published technique, not against a specific
adversary deployment.

## Two-node architecture

```
clients ──▶ Node A (ingress)  ──── WG tunnel ────▶  Node B (egress) ──▶ upstream
                 │                  ▲                       │
                 │                  │ initiated by B         │
                 ▼                  │                        ▼
            accepts inbound     persistent UDP            initiates outbound
            (TCP/443, etc.)                               (to upstream destinations)
```

| Node | Inbound | Outbound | Single-role from flow observer? |
|------|---------|----------|---------------------------------|
| A (ingress) | client TCP, WG UDP from B | none (packets travel **back through the tunnel B opened**) | yes — every flow A is part of was initiated by someone else |
| B (egress)  | none | persistent UDP to A, plus per-destination TCP/UDP to upstream | yes — every flow B is part of was initiated by B |

The non-obvious property: when Node A forwards a client packet
upstream, it does **not** open a new socket to the upstream — it
encapsulates the packet and sends it through the WG tunnel that B
already opened. From a flow-record observer's perspective, no new
flow leaves A's IP; the WG datagrams flow inside the pre-existing UDP
flow that B initiated. That is what restores the single-role
appearance on A.

This relies on **Node B being the WG initiator**, not the responder.
A reversed initiator role (A initiates) re-introduces the dual-role
signal on A. The role enforces initiator direction with
`PersistentKeepalive` on B and no keepalive on A; if upstream NAT
state expires, B re-initiates.

## Tunnel-layer choice: plain WireGuard

Evaluated against the requirement that **the tunnel layer must not
itself introduce a dual-role pattern on either node**.

| Candidate | Dual-role on A? | Dual-role on B? | Notes |
|-----------|-----------------|-----------------|-------|
| Plain WireGuard (chosen)            | no, if B initiates | no, B is the initiator anyway | One persistent UDP flow; no per-packet socket creation on A |
| ShadowTLS over Xray outbound from A | **yes** on A — A would initiate outbound to B | n/a | Rejected |
| Internal Xray inbound on A → Xray outbound to B | **yes** on A — A's outbound to B re-creates the dual-role signal | n/a | Rejected |
| Hysteria2 with B as initiator | no | no | Acceptable; deferred. Adds another encrypted tunnel surface to maintain |
| AmneziaWG with B as initiator | no | no | Same as WG with obfuscation; deferred until WG-shaped flow becomes itself fingerprinted |

Plain WG is the minimum-complexity choice that satisfies the
direction constraint. AmneziaWG-shaped variants can drop in later by
swapping the cohort file under `split-hop-egress`.

## Threat-model coverage

| Adversary capability | Mitigated by split-hop? |
|----------------------|-------------------------|
| Payload-shape DPI on client→A flows | No — independent; handled by per-transport obfuscation |
| Per-IP dual-role flow score on A    | **Yes** — A only accepts inbound |
| Per-IP dual-role flow score on B    | **Yes** — B only initiates outbound |
| Active probing of A's listeners     | No — handled by `honeypot` + `policy-ratelimit` roles |
| ASN-bucket TCP-freeze on B's egress | No — independent; handled by provider/zone choice |
| Cross-VPS correlation by RTT timing | **Partial** — adding two-VPS RTT noise makes timing correlation harder but not impossible. Out of scope for this ADR |

## Operational cost

- **Hosting:** 2× VPS at minimum (one A, one B). For a multi-region
  fleet, the multiplier compounds — every region needs its own (A, B)
  pair.
- **Provisioning surface:** doubles. Both nodes need separate
  Terraform roots, secrets, and SSH keys.
- **Latency:** an extra hop between A and B. For an EU-hosted pair
  (e.g. fi-hel1 ↔ de-fra1) the added RTT is ~10–25 ms; for cross-
  continent pairs it can exceed 100 ms.
- **Failure mode:** when B goes down, A's clients silently lose
  upstream reachability — A still answers TLS handshakes. The
  existing `watchdog` role needs a per-leg health check (TBD as a
  follow-up task).

## When to recommend

| Operator profile | Recommend split-hop? |
|------------------|----------------------|
| High-risk cohort (operator under direct attribution risk) | yes |
| Standard cohort, single-VPS budget | no — overhead exceeds the published mitigation value at the published detection rate |
| Multi-cohort fleet operator | per-cohort decision; consider split-hop only for the highest-risk cohort |

## Pilot stand procedure

See `docs/RUNBOOK-split-hop-pilot.md` for the operator-side runbook.
At a high level:

1. Provision two VPSes via existing Terraform roots — typically in
   different zones of the same provider, or different providers.
2. Generate two WireGuard keypairs and an optional PSK; load the paired
   `split_hop_ingress_secrets` block on Node A and
   `split_hop_egress_secrets` block on Node B.
3. Enable `vpn.enable_split_hop_ingress` on Node A with
   `allow_research_roles: [split-hop-ingress]`, then run `site.yml` against
   Node A's environment.
4. Enable `vpn.enable_split_hop_egress` on Node B with client-facing
   transports disabled, then run `site.yml` separately against Node B's
   environment. Node B remains the tunnel initiator.
5. Verify `shop0` tunnel health on both nodes, then separately exercise a
   transport runtime UID's marked policy route; an interface-bound diagnostic
   proves only tunnel/NAT reachability.
6. Collect 24–72 h of flow data from an upstream vantage (provider's
   flow logs, or a separate observation host). Validate the per-node
   dual-role score against the threshold the FOCI paper uses.

## Out-of-scope follow-ups

- `watchdog` per-leg health check.
- AmneziaWG-shaped tunnel variant.
- Per-cohort split-hop selector in the subscription generator
  (clients today carry a single A IP; the egress identity is
  invisible to them, which is correct).
- An `ansible-playbook` orchestrator that runs both nodes from a
  single `make split-hop-deploy` command.
