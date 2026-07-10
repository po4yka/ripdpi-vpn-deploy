# Cascade: decide per-leg health-check/watchdog as an EXCEPTION-tier gate

- [ ] #task Decide whether the inherited split-hop per-leg watchdog gap blocks registration or only promotion for the cascade roles #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔼

## Goal

Decide how the per-leg health-check / watchdog gap that split-hop already documents (but does not gate on) applies to the new cascade role pair: whether it blocks EXCEPTION-tier registration outright, or only blocks any future promotion beyond EXCEPTION/RESEARCH tier.

## Why now

The cascade's two-node shape inherits split-hop's known failure mode: when the far leg goes down, the ingress node still answers, so clients silently lose upstream reachability. Split-hop's own topology doc flags a per-leg health check as a TBD follow-up that was never enforced. Carrying the same unaddressed gap forward for the cascade would repeat a known "liveness ≠ working" weakness on a role that is, additionally, RU-jurisdiction and whitelist-dependent.

## Scope

- Decide: hard blocker for EXCEPTION-tier registration, or a promotion-only criterion (matching or diverging from split-hop's current unenforced precedent), with rationale.
- Add the chosen rule as a promotion-criteria entry in `docs/ROLE-TIERING.md` naming the per-leg watchdog as an explicit blocker.
- Specify the health signal at the class level: a per-leg liveness signal that distinguishes far-leg-down from ordinary transient failure (protocol-level, not just process/socket state).

## Out of scope

- No watchdog implementation or probe content — this is a gate decision plus a promotion-criteria doc entry.

## Ship definition

- [ ] A written decision (registration-blocker vs promotion-only) with rationale.
- [ ] `docs/ROLE-TIERING.md` carries a promotion-criteria entry naming the per-leg watchdog gap.
- [ ] The decision states whether it matches or diverges from split-hop's current (unenforced) treatment and why.

## Links

- `docs/RU-CASCADE-DECISION.md`
- `docs/SPLIT-HOP-TOPOLOGY.md`
- `docs/ROLE-TIERING.md`
- `docs/AUDIT-SILENT-FAILURE.md`
