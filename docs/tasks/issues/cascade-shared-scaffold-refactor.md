# Cascade: decide shared-scaffold refactor for split-hop + cascade ingress (deferrable)

- [ ] #task Decide whether to fold shared ingress conventions into one base now, or defer until split-hop graduates #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔽

## Goal

Decide whether the conventions shared between `split-hop-ingress` and the new cascade ingress role (secrets-block shape, `no_log` on key material, scoped-nftables-table, tier/guard wiring) should be factored into one literal shared base now, or deferred until split-hop itself has graduated past RESEARCH tier and carries test coverage proving a refactor is behavior-neutral.

## Why now

The cascade design deliberately reuses the *shape* of split-hop's scaffolding but not its contract. Today that reuse is a documented convention, not a structural guarantee, so the two ingress roles can drift. Turning "reuse the shape" into a shared base would make it a guarantee — but refactoring an already-RESEARCH-tier, unconfirmed-in-prod role (`split-hop-ingress`) carries its own regression risk. This is a lower-priority engineering-hygiene decision, explicitly deferrable, recorded so it is not silently forgotten.

## Scope

- Decide now-vs-defer, with the trigger for "defer" being split-hop's own tier graduation and/or behavior-neutral test coverage.
- If now: identify exactly which conventions are safe to share vs which are contract-specific and must stay separate (e.g. split-hop's directional invariants must NOT be shared).
- If defer: record the re-open trigger so it is revisited rather than dropped.

## Out of scope

- No role code — this is a refactor-timing decision.

## Ship definition

- [ ] A written now-vs-defer decision with the re-open trigger recorded.
- [ ] If proceeding, a list of shareable-vs-contract-specific conventions with directional invariants explicitly excluded from sharing.

## Links

- `docs/RU-CASCADE-DECISION.md`
- `docs/ROLE-TIERING.md`
- `docs/SPLIT-HOP-TOPOLOGY.md`
