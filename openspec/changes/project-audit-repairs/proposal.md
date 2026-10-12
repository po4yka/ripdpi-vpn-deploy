# Change: Repair project audit security and lifecycle defects

Task ID: `SEC-1791735853691219`

## Why

The source audit found incorrect client binding, service recovery, host selection,
recipient artifacts and release publication. These paths can share device credentials,
interrupt unrelated sessions, report empty verification as success or prevent installation.

## What Changes

- Repair all fifteen confirmed audit findings and the custom SSH socket bootstrap risk.
- Preserve private input admission and exact resource ownership on failure and retry.
- Add behavior regressions, run local checks and publish one reviewed repair PR.
- No intentional breaking CLI or secrets schema changes. No live deployment is included.

## Capabilities

### New Capabilities

- `audit-boundary-correctness`: regression contracts across the audited owner boundaries.

### Modified Capabilities

- None. Existing interfaces retain their names and schemas; the delta defines the repaired cases.

## Impact

- Ansible runtime roles, shared cloud-init, operator scripts, vpnd, release workflows and tests.
- No provider resource change, production dependency, credential rotation or live rollout.
