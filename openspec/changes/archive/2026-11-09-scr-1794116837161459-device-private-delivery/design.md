## Context

`Lifecycle` already has a private delivery path for `native` format: it writes one recipient artifact, publishes no grant and supports refresh with a new private output. `ripdpi` and `singbox` issue always minted a subscription token for `publishers[0]` and refresh always required an active grant. `load_manifest` refused `ripdpi`/`singbox` delivery without publishers. See proposal.md for motivation.

## Goals / Non-Goals

- Goal: issue and refresh a device with REALITY, XHTTP and Hysteria2 transports on a fleet without a publisher, with the same encrypted journal, runtime adoption and native access checks.
- Non-goal: a new delivery format, a subscription publisher or changes to revocation.
- Non-goal: expiry without a publisher; nothing could enforce it.

## Decisions

- Generalize the native flag to `private`: delivery is private when the format is `native` or the manifest has no publisher. Every existing check that keyed on native delivery (output admission, grant checks, artifact presence in the journal) keys on `private`. Rejected: a new `private` delivery format, which would duplicate `ripdpi`/`singbox` rendering and change the manifest contract.
- Private `ripdpi`/`singbox` artifacts use the existing artifact shape: `profile` holds the rendered payload, `amneziawg_configs` and `naive_uris` come from `native_delivery`, `subscription_url` is `null`. The registry entry keeps an empty `token_hash_prefix`.
- `load_manifest` replaces `subscription-delivery-needs-publisher` with `private-delivery-does-not-enforce-expiry` and requires an output path for every private delivery.

## Risks / Trade-offs

- A private artifact has no refresh URL → the operator refreshes with a new private output; `emit-incy` reads current SOPS state for INCY links.
- Removing a refusal widens accepted manifests → only the no-publisher case changes; tests cover issue, refresh and the expiry refusal.

## Migration Plan

Additive for fleets with publishers. Rollback is a revert; a device issued privately stays valid and is revoked by the unchanged revocation path. Gates: the device lifecycle unit tests, `make docs-check`, then `make check` because the change touches secrets handling; PR CI on the exact head.
