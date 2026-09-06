## Context

The implementation was first treated as tooling-only. Review identified the
required-status migration as a security control, so this specification records
and gates the existing implementation before any live protection change.

## Goals / Non-Goals

- Goal: run every affected consumer with strict admission and conservative fallback.
- Non-goal: change runtime deployment, reduce baseline tests or split role matrices.

## Decisions

- Use a standard-library Python dependency graph, with consumer closure and a
  conservative full plan for shared/unknown paths. No new dependency is needed.
- Compare base to tested merge with NUL-delimited Git output and rename detection
  disabled, preserving old names. An invalid history selects the full graph.
- Retain all matrix commands; apply only job-level selection. Keep all pytest
  shards and static/security baseline checks unconditional.
- Validate exact plan and result key sets in the final always-running gate.
  Generic acceptance of skipped jobs would hide failed dependencies.

## Contracts and ownership

- Codex owns scripts/select-ci-checks.py, scripts/check-ci-results.py, CI and
  protection workflows, their regression tests, documentation and task artifacts.
- Terraform roots, Ansible roles, vpnd interfaces and secrets are unchanged.
- GitHub Actions check names and required-status contexts are the changed contract.
- Work is isolated in a dedicated worktree; the root checkout's merge is preserved.

## Risks / Trade-offs

- Missing dependency edges could omit tests: shared/unknown changes select all,
  explicit embedded-doc consumers are tested, main/manual always run full CI.
- Full pytest remains the lower bound on PR latency, intentionally preserving
  broad dynamic Python import/fixture coverage.
- Aggregate checks require correct plan validation: regressions cover malformed
  maps, failures, cancellation and unexpected skips as well as real Git histories.

## Migration Plan

1. Validate regressions, actionlint, strict zizmor, task contracts and make validate.
2. Observe complete and selective hosted runs; full integration must be green.
3. PATCH required contexts only, preserving strict mode and existing app bindings;
   compare full protection readback to ensure unrelated settings are unchanged.
4. Merge through protected main and observe full CI on its exact SHA before closure.
5. Roll back by restoring unconditional scheduling and the prior canonical context
   set together after green full CI. Never disable or bypass protection.
