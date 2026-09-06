## Context

The deploy repository owns the canonical RIPDPI bundle schema and AWG source
pins. AWG parameters have a fingerprint, but neither the entry nor fingerprint
names the wire revision. The current client implements one pinned semantic line.

## Goals / Non-Goals

- Goal: make wire compatibility explicit and fail closed across repositories.
- Goal: support a staging-only later revision without changing current behavior.
- Non-goal: select production parameters or promote a new revision live.

## Decisions

- Add a required revision field at the AWG-entry boundary and immutable public
  implementation provenance alongside it.
- Version the fingerprint preimage so revision substitution changes identity.
- Keep the top-level bundle compatible only if old clients can safely reject the
  revised entry; otherwise make the breaking schema change explicit and update
  the RIPDPI consumer before emission.
- Extend the existing source watcher to open/hold staging work, never auto-promote.

## Contracts and ownership

- Deploy owns canonical schema, emission, pins, staging cohort, and public goldens.
- RIPDPI owns parsing, activation refusal, runtime selection, and client interop.
- Shared contract artifacts remain byte-identical and are checked in both CI systems.

## Risks / Trade-offs

- A strict revision field can reject old bundles; migration must preserve an
  explicit current value and sequence server/client rollout safely.
- Upstream naming may be ambiguous; map it to repository-owned stable revisions.
- A source release is not field proof; staging acceptance remains mandatory.

## Migration Plan

Land canonical schema and fixtures, update the RIPDPI consumer, then enable a
staging cohort for the later revision. Keep production on the current revision
until client, staging, and physical-device evidence pass. Rollback disables the
staging cohort and restores the prior emitted contract.
