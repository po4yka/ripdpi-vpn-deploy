# CIC-1788684721834869: Select CI checks from changed-file dependencies

## Objective

Select CI checks from changed-file dependencies

## Ownership

Codex owns the CI selector and result gate, ci.yml, related regression tests,
branch protection contexts, testing documentation and this task. Work is isolated
in the ci-dependency-selection worktree; the shared root's unfinished merge is
untouched. The change affects CI admission controls but does not alter deployed behavior.

## Execution

- [x] CIC-1788684721858733 Define implementation and verification #chore !high @item:CIC-1788684721834869
- [ ] CIC-1788686155608641 Deliver protected main and verify the pushed full CI run #chore !high @item:CIC-1788684721834869

## Verification

- Local selection regressions cover real multi-commit and advanced-base merge
  histories, renames/deletions, unknown inputs and every selected failure,
  cancellation or unexpected skip. Related regression suites, governance checks,
  actionlint, strict offline zizmor and applicable pre-commit hooks passed.
- Independent specification review found no correctness defects. Standards
  review found stale Terraform/Trivy frequency claims; the follow-up fixes those
  and Renovate guidance and adds the advanced-base merge regression.
- Full hosted CI on 8dec2d47d38f4617f2f2058e02ce32eae3070e01 selected all 28
  consumer job groups and passed: GitHub Actions run 34023710390 (success).
- Selective hosted CI on 76f7b8db381513ca0f862ebc3bd78b41758856b7 selected Rust
  and native runtime for two actual docs/test changes. It passed with 19 executed
  jobs and 14 planned group skips, including the strict final gate:
  GitHub Actions run 34023851656 (success).
- Live protection migration, protected main delivery and exact-main full CI
  remain pending. This task is not closed on branch-only evidence.
