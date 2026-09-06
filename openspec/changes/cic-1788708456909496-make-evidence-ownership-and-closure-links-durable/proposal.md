# Change: Make evidence ownership and closure links durable

Task ID: `CIC-1788708456909496`

## Why

The task lifecycle currently rejects every incoming reference when a terminal
task is purged, while the proposed proportional-verification policy requires an
operational task to retain a link to a completed source task. Removing the link
loses evidence ownership; retaining it blocks the mandatory purge. The policy
also changes closure semantics without its own tracked OpenSpec owner and does
not state that authenticated client traffic requires the separate client
evidence category.

## What Changes

- Active tasks can retain validated non-blocking evidence-ownership links to
  locally purged `done` tasks through their committed terminal history.
- Unsafe parent links, unresolved blockers, dropped history, malformed terminal
  transitions, and ambiguous task incarnations continue to fail closed.
- Proportional verification explicitly requires client-layer evidence for
  authenticated client traffic and cannot turn existing required or blocked
  evidence into `passed` or `not_applicable` without proof or an exact mapped
  transfer. Current failed or unavailable observations may remain `blocked`.
- Task-lifecycle policy changes are owned and verified by this OpenSpec change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci/task-contract-validation`: Validate durable local task references and the
  evidence-category rules used by task closure.

## Impact

- Task contract and history resolution in `scripts/tasks/taskctl.py`.
- Existing task-contract regression tests and lifecycle documentation.
- No Terraform, Ansible, secret, provider, host, client, or deployment mutation.
