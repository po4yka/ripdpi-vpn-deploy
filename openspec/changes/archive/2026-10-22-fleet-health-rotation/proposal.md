# Change: Repair fleet health and resumable rotation boundaries

Task ID: `OPS-1792654666090980`

## Why

Fleet status bypasses admitted inventory transport and equates a TCP listener
with working VPN access. Rotation uses the same insufficient reachability
signal for its availability floor and resumes by array index without binding
the saved progress to the reviewed plan.

## What Changes

- Collect fleet status through existing strict inventory-bound SSH, keeping
  passive observations separate from authenticated client-path health.
- Require fresh authenticated protocol evidence for distinct surviving nodes
  before rotation can satisfy `min_active`.
- Bind private, serialized, durable rotation progress to the exact plan;
  refuse changed plans and uncertain interrupted external steps.
- BREAKING: fleet-status requires an admitted inventory and replaces legacy
  ASN/version/burn columns with source and categorical observation columns.
- BREAKING: rotation plans require a version and explicit health configuration
  and node mapping. Unbound legacy progress is not accepted for resume.

## Capabilities

### New Capabilities

- `operations/fleet-health-rotation`: strict passive fleet status, authenticated
  survivor admission, and plan-bound resumable rotation.

### Modified Capabilities

- None. Reuse existing inspection and protocol-liveness contracts unchanged.

## Impact

- Operator scripts, their Make/vpnd call sites, fixtures and regression tests.
- No new dependency, provider resource, credential authority, protocol engine,
  deployment, credential rotation or production acceptance is included.
- The source outcome includes reviewed changes, local validation, protected PR
  merge and exact-revision main CI acceptance.
