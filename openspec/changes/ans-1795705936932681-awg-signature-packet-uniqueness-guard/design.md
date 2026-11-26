## Context

The signature admission and canonical fingerprint come from `awg-range-signature-profile`. The per-instance header, padding and port guard comes from `awg-per-instance-wire-shape`.

## Goals / Non-Goals

- Goal: Keep signature packets unique per instance so that no packet becomes a shared fleet signature.
- Non-goal: any IP address, hostname, key or concrete evasion parameter in the repository.

## Decisions

- Assumption: compare the canonical static bytes of each program, not the random generators. Step 1 defines the comparison on the canonical form of the first change.
- Assumption: the default list holds SHA-256 digests only, so the repository holds no ready-made signature.
- Assumption: the guard reuses the production and staging split of the header guard.

## Contracts and ownership

- `ansible/roles/amneziawg/` and `docs/reference/awg-cohorts.md`. Starts after both related changes merge. One writer.

## Risks / Trade-offs

- A new public default appears after the list is pinned -> the list is a data file with a dated note; extending it is a small change.
- Random packets can be rejected by the peer admission rules -> generation stays inside the admitted bounds and the existing admission tests run on generated output.

## Migration Plan

Forward only. Rollback reverts the change.
