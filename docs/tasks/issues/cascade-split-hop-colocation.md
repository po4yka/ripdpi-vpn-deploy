# Cascade: decide cascade-ingress vs split-hop co-location on a single node

- [ ] #task Decide whether a cascade ingress role may share a node with split-hop roles; default mutually-exclusive #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔼

## Goal

Answer, in a follow-up ADR, whether the new cascade ingress/egress role pair may ever co-exist on the same node as the existing `split-hop-ingress` / `split-hop-egress` roles, and encode the answer as a structural role-compatibility rule.

## Why now

The two role pairs serve different threat models with partly contradictory directional invariants: split-hop exists to defeat a dual-role flow-correlation classifier (initiator-must-be-B, no-listen-on-B), whereas a cascade entry node is by definition client-facing and originates RU-destined egress. Mixing both on one node risks inverting split-hop's documented guarantee. The cascade decision defaults these to mutually-exclusive until this is settled; leaving it implicit invites an accidental co-enable.

## Scope

- Decide mutually-exclusive vs conditionally-compatible on a single node, with the reasoning recorded in `docs/RU-CASCADE-DECISION.md` (or a dedicated ADR).
- If mutually-exclusive: specify a structural `pre_task`-style assert that blocks both role families being enabled on one host.
- If conditionally-compatible: specify that both the jurisdiction-exception gate and the existing research-tier gate must pass independently (AND, not OR), and how the two nftables/table scopes stay non-overlapping.

## Out of scope

- No role implementation or nftables rule content — this is a compatibility decision plus a guard-shape proposal.

## Ship definition

- [ ] A written decision (mutually-exclusive or conditional) with rationale lands in the cascade ADR.
- [ ] The role-compatibility rule is specified at the structural-assert level (names as proposals).
- [ ] The decision references split-hop's directional invariants and why they do not transfer.

## Links

- `docs/RU-CASCADE-DECISION.md`
- `docs/SPLIT-HOP-TOPOLOGY.md`
- `docs/ROLE-TIERING.md`
