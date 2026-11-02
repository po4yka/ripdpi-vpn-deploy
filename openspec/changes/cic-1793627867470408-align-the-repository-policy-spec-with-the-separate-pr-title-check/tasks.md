# CIC-1793627867470408: Align the repository policy spec with the separate PR title check

## Objective

The canonical `repository-policy` spec names `PR title` as a branch-required
context and states that a title edit reruns only the title check.

## Ownership

`openspec/changes/cic-1793627867470408-align-the-repository-policy-spec-with-the-separate-pr-title-check/`
and, through archive, `openspec/specs/repository-policy/spec.md`. No other path.

## Execution

- [x] CIC-1793628619386753 Restate REQ-RPOL-LAYERS and REQ-RPOL-MERGE for the branch-required PR title context and validate the change strictly #bug @item:CIC-1793627867470408

## Verification

- Local: `./taskctl openspec cli validate <change> --strict`, `make task-check`,
  `make docs-check`.
- Remote CI: the pull request's `required checks`, CodeQL and `PR title` contexts.
- Dry-run, staging, live, client and artifact gates do not apply: the change
  edits only planning and spec text.
