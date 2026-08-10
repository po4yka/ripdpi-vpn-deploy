# Change: Emit a versioned AmneziaWG protocol-revision contract

Task ID: `SCR-1786299499104067`

## Why

The bundle currently describes AWG parameters without naming the wire revision
that gives those parameters meaning. A later server revision could therefore be
parsed as the current one and fail opaquely on the client.

## What Changes

- Add explicit revision and implementation provenance to canonical AWG entries.
- Bind parameter fingerprints and validators to the declared revision.
- Keep the current revision unchanged and make later revisions staging-only.
- Make unknown or inconsistent revisions fail before profile activation.

## Capabilities

### New Capabilities

- `amneziawg-revision-contract`: Emit and validate revision-aware AWG profiles.

### Modified Capabilities

- `ripdpi-bundle`: Carry explicit AWG wire semantics across the deploy/client boundary.

## Impact

- Affects the canonical bundle schema, emitter, public source metadata, fixtures,
  source watching, staging cohorts, and the vendored RIPDPI contract.
- No production revision promotion is authorized.
