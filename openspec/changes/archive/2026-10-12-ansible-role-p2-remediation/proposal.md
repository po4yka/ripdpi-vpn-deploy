# Change: Repair P2 role lifecycle and configuration contracts

Task ID: `ANS-1791562764586678`

## Why

The role audit identified 32 P2 defects in transport contracts, predictive
execution, enabled-to-disabled reconciliation, authority publication,
enforcement and monitoring evidence. These need repair against the reviewed
P1 branch rather than against the older audit snapshot. Six P2 investigation
points also need bounded verification so demonstrated defects are repaired
and unproved claims remain explicitly qualified.

## What Changes

- Converge complete TLS, SSH, listener and exact-version contracts.
- Apply binary/unit changes to running services and retire owned disabled or
  removed runtime without deleting unrelated state or retained recovery data.
- Validate complete candidates and preserve prior working authority when
  nginx, geodata or retained receiver activation fails.
- Preserve dynamic enforcement, bounded detector state, atomic health/budget
  evidence and true check-mode behavior.
- Verify already-integrated repairs and preserve every P1 safety boundary.
- BREAKING: invalid or unsupported transport/version combinations are replaced
  with the supported contract and every affected repository consumer updated.

## Capabilities

### New Capabilities

- `security/ansible-role-p2-lifecycle`: complete role ownership, lifecycle,
  publication and evidence guarantees for the audited P2 paths.

### Modified Capabilities

- None; existing capability contracts are preserved unless a proven audited
  defect requires an explicitly documented contract correction.

## Impact

- Ansible runtime roles, site dispatch, listener/profile/schema consumers,
  directly related tests, role notes and intended render snapshots.
- Existing PR 282 receives incremental source commits from its P1 revision.
- No provider mutation, fleet deployment, real credentials, private state
  migration or activation of retired monitoring topology is authorized here.
