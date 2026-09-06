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
- Full hosted CI on 87f1c33de83216f926d806f1c306b7b6aada06ee selected all 28
  consumer job groups: 75 successful jobs, zero failed jobs, final gate success.
- Selective hosted CI on 76f7b8db381513ca0f862ebc3bd78b41758856b7 selected Rust
  for embedded docs and native runtime for a changed unit test. Observed outcome:
  19 successful executed jobs, 14 planned group skips and final gate success.
- Live protection readback matched all nine canonical required contexts with
  app_id 15368 and strict mode enabled. Full before/after comparison confirmed
  every unrelated protection setting unchanged.
- Protected main delivery and exact-main full CI remain pending. This task is
  not closed on branch-only evidence.
