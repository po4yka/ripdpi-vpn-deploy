# Change: Unify device issuance refresh and complete revocation

Task ID: `OPS-1792679812321846`

## Why

Device authority is currently spread across protocol lists, per-node registries
and subscription publishers. Manual revocation can leave one live credential
or URL behind, and interrupted issuance has no fleet-wide continuation record.

## What Changes

- Add one reviewed private operation for enrollment, payload refresh and full
  revocation across an explicit complete fleet inventory and its authorities.
- Show exact affected nodes, transports and grants before mutation; retain
  encrypted intent and reconcile actual state after interruption.
- Preserve unrelated devices, keep ordinary refresh URLs and expiries stable,
  and write recipient artifacts only to an explicit private destination.
- Revoke every discovered device credential and subscription grant, converge
  each affected node through canonical gates, and verify old access fails.
- Keep unavailable nodes or incomplete verification visibly unfinished.
- Add optional operation journals to the secrets schema. Existing specialized
  commands remain distinct transport operations; full device status is owned
  by the new fleet operation.

## Capabilities

### New Capabilities

- `clients/device-lifecycle`: reviewed resumable fleet-wide device operations.

### Modified Capabilities

- None. Existing individual transport operations keep their documented scope.

## Impact

- SOPS schema and operator scripts; canonical Make entry point, Ansible runtime
  convergence and bounded native credential checks; subscription publication.
- Reuses device-migration publisher CAS and strict private transport helpers
  after that feature is integrated. No provider mutation or new cloud service.
- Source/CI implementation scope only; no live credentials or fleet changes are
  authorized by this implementation request.
