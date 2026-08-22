## Context

The two credentialed workflows predate the repository's GitHub Actions
security gate in spirit but passed zizmor's default persona: the label trigger
plus fork check was judged sufficient, and the two direct `${{ secrets.* }}`
interpolations sat in steps written before the env-indirection convention was
codified. The audit demonstrated that a same-repo branch defeats the fork
check by construction, and that template expansion into `run:` text is an
execution primitive, not a formatting risk.

## Goals / Non-Goals

- Goals: make reviewer approval a hard second factor for credentialed runs;
  remove secret values from the template-expansion surface; keep both
  invariants machine-checked locally.
- Non-Goals: migrating the `CI_*` secrets into environment-scoped secrets
  (values are operator-managed; repo-level secrets behind an approval gate
  give the same protection); changing what the workflows deploy; adding
  approval flows to non-credentialed jobs.

## Decisions

### D1 — Protected GitHub Environment as the gate (chosen)

A required-reviewer environment is enforced server-side: the job cannot start
until the deployment is approved, independent of workflow file contents on the
PR head. Alternatives rejected:

- Removing the label trigger entirely loses the documented PR-integration
  flow (`docs/CI-REAL-DEPLOY.md`).
- Checking approvals inside the job is circular: the checking code comes from
  the untrusted PR head.

The environment is provisioned through the GitHub API because a workflow
reference to a missing environment auto-creates an unprotected one — the gate
must exist before the reference does.

### D2 — Step-level `env:` indirection (chosen)

Matches the pattern already used by adjacent steps ("Verify required secrets
are present", "Generate synthetic CI secrets") and the fix pattern applied to
the reusable Rust workflow during the zizmor change. Quoted expansion keeps
GitHub's log masking intact.

### D3 — Contract test over lint rule (chosen)

A pytest contract test asserts `environment:` on both jobs and forbids
`${{ secrets.` inside any `run:` block of either file. A dedicated zizmor
config rule would duplicate the audit that already covers this class; the
contract test runs in the fast local gate where contributors actually iterate.

## Risks / Trade-offs

- Every scheduled run now waits for manual approval — accepted friction;
  `can_admins_bypass` remains true so the solo maintainer can approve from the
  deployments activity log.
- `[ "${CI_SSH_PRIVATE_KEY}" ... ]` style handling must stay quoted; shellcheck
  and existing conventions cover this.

## Migration Plan

Single commit sequence on the fixes branch: environment provisioned via API,
workflows updated, contract test added. No state migration; no runtime impact.

## Open Questions

- None.
