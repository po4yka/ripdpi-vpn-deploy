# Change: Require committed review before terminal close

Task ID: `CIC-1788741692326070`

## Why

`taskctl close prepare --outcome done` can currently consume an uncommitted
working-tree transition to `review`. The resulting terminal commit then has no
durable reviewed predecessor, so later history validation cannot distinguish a
reviewed close from a direct non-terminal-to-done transition. The closure
contract and its canonical operator workflow need one explicit committed-review
boundary.

## What Changes

- Done closure requires the selected task to exist at the same repository path
  in `HEAD` with the same task ID and `status: review`.
- Refusal occurs before issue or receipt mutation; a committed review snapshot
  continues through the existing archive, terminal-commit, and purge lifecycle.
- The canonical OpenSpec archive workflow requires the review-state commit
  before archival and close preparation.
- The committed-review check reads only the selected task record rather than
  scanning every active task in Git.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci/task-contract-validation`: Require a committed review snapshot before
  preparing a done task and keep the documented archive workflow executable.

## Impact

- Repository-local task lifecycle code and regression tests.
- The repository-pinned OpenSpec archive skill and its generated-asset digest.
- No Terraform, Ansible, secret, provider, host, client, or deployment mutation.
