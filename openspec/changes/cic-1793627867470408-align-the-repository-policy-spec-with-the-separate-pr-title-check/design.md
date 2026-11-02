## Context

See proposal.md. The implementation shipped in po4yka/ripdpi-vpn-deploy#469:
`.github/workflows/pr-title.yml` runs `scripts/check-pr-title.py`, `ci.yml` no
longer listens to `edited` and has no `pr-title` job, and
`.github/repository-policy.json` lists `PR title` as a required context. Only the
canonical spec still describes the earlier design.

## Goals / Non-Goals

- Goal: the canonical `repository-policy` spec states the merge gate that the
  configuration and workflows enforce.
- Non-goal: changing any workflow, script, test or repository setting.
- Non-goal: applying the policy to GitHub; that stays an operator action.

## Decisions

- Modify the spec to match the shipped design. Rejected alternative: restore the
  title check inside the `required checks` aggregate. That brings back the
  full-plan restart on every edit, which used about 11% of CI runner time.
- Keep the scenario that rejects a same-named context from another app explicit,
  because a separate required context is easier to spoof than a job inside the
  aggregate if the app binding is lost.

## Contracts and ownership

- `openspec/specs/repository-policy/spec.md` (through archive).
- Enforced by `.github/repository-policy.json`, `.github/workflows/pr-title.yml`,
  `tests/unit/test_pr_title.py` and `tests/unit/test_branch_protection_contract.py`.

## Risks / Trade-offs

- Until an operator runs `make repository-policy-apply`, GitHub does not yet
  require `PR title`, so an invalid title can merge. Mitigation: the operator
  applies the reviewed policy; `make repository-policy-plan` shows the pending
  context.

## Migration Plan

Archive syncs the delta into the canonical spec. Rollback is a revert of the
archive commit. No runtime, deployment or client rollout applies.
