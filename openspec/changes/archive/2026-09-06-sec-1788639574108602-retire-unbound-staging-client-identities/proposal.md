# Change: Retire unbound staging client identities after verified cleanup

Task ID: `SEC-1788639574108602`

## Why

Disposable staging can issue an encrypted client identity before executor
binding, promotion, or sentinel publication succeeds. Once the exact staging
server is gone, the existing de-onboarding command refuses because those later
artifacts are absent. Operators need a supported recovery path instead of an
unreviewed direct SOPS edit.

## What Changes

- Add a separate unbound-retirement command that accepts only an original
  staging intent, its cleanup manifest, and canonical verified provider
  absence/state-zero evidence.
- Remove exactly one issued client from all required encrypted collections in
  one serialized, compare-bound SOPS transaction.
- Persist a private recovery journal and terminal receipt so interruption is
  replayable and partial or foreign state remains fail closed.
- Add an early literal-safe Make entrypoint and behavioral failure-boundary
  tests without reading real secrets or contacting providers.

## Capabilities

### Modified Capabilities

- `clients/config-registry`: support recovery retirement of an issued,
  staging-only client whose executor was never bound or promoted.

## Impact

The change touches one stdlib operator controller, the Make operator surface,
the client registry specification, tests, and task evidence. It performs no
provider, host, network, Tailnet, or production mutation by itself.
