# Change: Carry a per-entry allowlist-regime survivability label in the client bundle

Task ID: `SCR-1795705796387934`

## Why

Public observations of an allowlist regime on cellular access describe UDP toward non-permitted addresses as blocked broadly. They describe only standard HTTPS toward permitted addresses as completing. The source is one author and the statement is a reader inference. Treat it as single-source and unverified.

If the observation holds, a client under that regime wastes attempts on UDP-based entries. A per-entry label lets the client skip them once it detects the regime. The label describes the transport class only. It does not say that an address is permitted.

## What Changes

- Add an optional per-entry label to the bundle contract and to `scripts/validate-bundle.py` and `contract/negative/` fixtures.
- Add a repository-owned class table: UDP-based classes get no, the standard TLS-over-TCP class gets yes, everything else gets unknown.
- Update `docs/reference/ripdpi-bundle.md`.
- BREAKING when bundle v3 has already shipped: then the label needs a version bump, with no compatibility shim. Step 1 decides this from the state of D4 (`SCR-1795086521848661`) and D1 (`SCR-1795085709140075`).
- RIPDPI counterpart: read the label in failover and skip entries marked no when the client detects the allowlist regime. Tracked in the RIPDPI repository; no ID is recorded here.

## Capabilities

### New Capabilities

- `clients/bundle-allowlist-survivability`: per-entry allowlist-regime survivability label in the client bundle.

### Modified Capabilities

- None.

## Impact

- Contracts: `contract/ripdpi-bundle.schema.json`, `contract/negative/`, `scripts/validate-bundle.py`, `scripts/emit-bundle.sh`, `scripts/client_payload.py`, `docs/reference/ripdpi-bundle.md`.
- Cross-repository: the vendored copy in the RIPDPI client repository.
