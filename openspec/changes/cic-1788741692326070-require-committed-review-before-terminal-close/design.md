## Context

The canonical lifecycle commits `review`, prepares and commits a terminal
record, then purges in a later commit. Before this change, `close prepare`
validated only the working task state, so a working-tree-only `doing -> review`
edit could be folded into the terminal commit. Historical validation would then
see `doing -> done` and correctly reject the eventual purge, but the operator
would discover the violation only after the irreversible lifecycle had begun.

The first implementation guarded done closure by building the complete
historical task snapshot map at `HEAD`. That was correct but started one
`git show` process per active issue even though the selected task path was
already known.

## Goals / Non-Goals

- Goal: refuse done closure unless the same selected task is committed in
  `review`, before any mutation.
- Goal: keep the canonical archive skill ordered so the guard can succeed.
- Goal: make guard cost independent of the number of unrelated active tasks.
- Goal: let a published simple-work task adopt OpenSpec without fabricating a
  verification record in its pre-OpenSpec commits.
- Non-goal: change historical purge validation, evidence ownership, task status
  transitions, or OpenSpec archive receipt semantics.
- Non-goal: mutate Terraform, Ansible, secrets, providers, hosts, clients, or
  deployed services.

## Decisions

- Pass the selected `Document` to the guard. Its repository-relative issue path
  and task ID are the exact identity that `close prepare` is about to mutate.
- Read only `HEAD:<selected-path>` through the existing `git_show_text` helper,
  parse it with the normal task-document parser, and require both matching ID
  and `review` status. A missing path, rename, ID mismatch, malformed document,
  or non-review status fails closed.
- Keep the guard immediately before verification and archive-state checks, and
  after the working-state `review` check. No terminal artifact is written until
  all these preconditions pass.
- Update the repository-pinned archive skill in place and refresh only its
  tamper-evident generated-asset digest. Compatibility skill roots are symlinks
  and therefore require no duplicate content edit.
- Verify bounded lookup by command shape and count, not wall time. Timing tests
  are noisy; one exact `git show` and zero `git ls-tree` calls prove the desired
  scaling contract deterministically.
- Build evidence observations only from historical snapshots whose own
  `spec_mode` is `required`. Retain every such snapshot, including snapshots
  separated by another mode or naming a prior OpenSpec change, and include all
  observed change paths in the Git history query. This excludes history that
  cannot own a verification file without letting a later mode or change-name
  transition erase earlier required evidence.

## Contracts and ownership

- `scripts/tasks/taskctl.py`: selected committed-review lookup and close
  precondition.
- `scripts/tests/test_taskctl.py`: refusal, success, identity/path, and bounded
  Git-read regressions.
- `.agents/skills/openspec-archive-change/SKILL.md`: operator sequencing.
- `tools/tasking/generated-assets.lock.json`: digest for the changed canonical
  generated skill.
- `docs/tasks/issues/` and this OpenSpec change: portfolio, requirements,
  execution, and evidence ownership.

## Risks / Trade-offs

- A working task rename now fails even if an older path contains the same ID.
  This is intentional: the exact selected record must have a durable reviewed
  predecessor, and an explicit rename commit supplies it.
- Parsing a single temporary file retains the normal frontmatter validation and
  error behavior while avoiding a broader history-parser refactor.
- A later upstream skill regeneration can restore the old ordering. The locked
  digest makes that drift fail validation until the repository policy patch is
  reapplied.

## Migration Plan

1. Add the OpenSpec ownership and convert the existing task from simple to
   required execution without changing its stable task or step IDs.
2. Add RED regressions for selected-record lookup and the canonical workflow.
3. Replace the portfolio-wide committed-review lookup with one selected-path
   read; update the skill and its digest.
4. Run focused taskctl tests, skill/lock checks, base-aware task validation,
   `make task-check`, `git diff --check`, and the complete repository gate.
5. Commit the updated task in `review`, push the same PR, and require every
   protected check plus a clean final review before merge.
6. Exercise archive readiness against the published pre-OpenSpec task history
   before preparing terminal closure.

Rollback is a normal revert before any later task uses the new closure guard.
After adoption, reverting requires restoring the former operator workflow and
reviewing any terminal lifecycle produced under the stricter contract; no
runtime or infrastructure rollback exists.
