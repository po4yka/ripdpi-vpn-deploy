# Change: Align the repository policy spec with the separate PR title check

Task ID: `CIC-1793627867470408`

## Why

Pull request po4yka/ripdpi-vpn-deploy#469 moved the PR title and commit-subject
check out of `ci.yml` into its own `pr-title.yml` workflow. Before that change,
every title or description edit cancelled the running CI plan and restarted it
for the same head commit. In nine days of history this repeated 87 PR runs and
used about 11% of all CI runner time. The check result is now the separate
branch-required context `PR title`, not a job inside the `required checks`
aggregate.

The canonical `repository-policy` spec still says that the title result must
reach the required CI aggregate and lists only `required checks` and the two
CodeQL contexts as branch requirements. Operators and agents who audit or change
the merge policy read a requirement that the implementation no longer meets.

## What Changes

- The CI ruleset requirement names `PR title` as a fourth branch-required
  context from GitHub Actions.
- The merge requirement states that the title and commit-subject check runs in
  its own read-only workflow on opened, synchronized, reopened and edited pull
  requests, that its result is a branch-required context, and that an edit does
  not restart the complete CI plan for an unchanged head commit.
- No implementation change: `pr-title.yml`, `ci.yml` and
  `.github/repository-policy.json` already match the modified requirements.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `repository-policy`: REQ-RPOL-LAYERS gains the `PR title` context;
  REQ-RPOL-MERGE moves the title result from the CI aggregate to its own
  branch-required context and adds the no-restart property for edits.

## Impact

- Canonical spec `openspec/specs/repository-policy/spec.md` after archive.
- No Terraform, Ansible, secrets, vpnd, client or runtime change.
- The GitHub ruleset itself changes only when an operator applies the existing
  `.github/repository-policy.json` with `make repository-policy-apply`; that
  live action is outside this change.
