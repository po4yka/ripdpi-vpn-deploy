# SEC-1788275314490012: Resolve current CodeQL and Scorecard code scanning alerts

## Objective

Eliminate alerts 341–344, 424, and 511–513 at their source while preserving
typed Tailnet failures, AWG validation, image publication, and SARIF upload.

## Ownership

- Python lane: `scripts/tailnet-network-promotion.py`,
  `scripts/vpn-protocol-liveness.py`, and their focused unit tests.
- Workflow lane: `.github/workflows/publish-molecule-debian13.yml`,
  `.github/workflows/publish-molecule-ubuntu2404.yml`, and one focused workflow
  permission contract test.
- Planning lane: this change and
  `docs/tasks/issues/current-code-scanning-remediation.md`.
- All writes are serialized in worktree `/tmp/ripdpi-code-scanning-20260901`;
  unrelated worktrees and the conflicted primary checkout remain untouched.

## Execution

- [x] SEC-1788275548576527 Make Tailnet snapshot descriptor cleanup explicit and add focused canonical-failure tests #bug !high @item:SEC-1788275314490012
- [x] SEC-1788275549110334 Remove the unused AWG parse result while preserving pre-mutation validation and focused tests #bug !high @item:SEC-1788275314490012
- [x] SEC-1788275549618803 Scope Molecule image workflow write permissions to publish jobs and prove local plus hosted behavior #bug !high @item:SEC-1788275314490012

## Verification

- Focused: Tailnet promotion cleanup, protocol-liveness AWG validation, and
  publication-workflow permission contract tests.
- Local security: actionlint and repository-pinned zizmor on both affected
  workflows; CodeQL-compatible Python compilation/static checks where locally
  available.
- Aggregate: `make ci-fast` and `make validate`, with every environment-only
  blocker recorded by exact command and output instead of treated as success.
- Hosted: exact implementation SHA passes CodeQL Python and Scorecard; GitHub
  reports alerts 341–344, 424, and 511–513 as `fixed`, not dismissed.
- Publication: an authorized hosted run proves GHCR publication and SARIF upload;
  local YAML validation is not publication evidence.
