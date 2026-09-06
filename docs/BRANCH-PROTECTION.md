# Branch protection

`main` requires every CI gate to pass before merge, plus a pull request,
linear history, conversation resolution, and admin enforcement. Approving
reviews are not required while this is a single-maintainer repository because
GitHub does not allow an author to approve their own pull request. The default
`GITHUB_TOKEN` does **not** carry `Administration: write`, so the
protection rule is applied through `.github/workflows/branch-protection.yml`,
gated on a fine-grained personal access token (PAT).

## One-time setup

### 1. Create the PAT

GitHub → Settings → Developer settings → Personal access tokens →
**Fine-grained tokens** → Generate new token.

| Field | Value |
|---|---|
| Token name | `vpn-deploy branch-protection` |
| Expiration | 1 year (set a reminder) |
| Repository access | Only the `ripdpi-vpn-deploy` repository |
| Repository permissions → Administration | **Read and write** |
| Repository permissions → Contents | Read |

Other permissions stay at default (no access). Save the token.

### 2. Save the token as a repo secret

GitHub → repo Settings → Secrets and variables → Actions → New repository
secret:

- Name: `BRANCH_PROTECTION_TOKEN`
- Value: paste the PAT

### 3. Run the workflow

GitHub → Actions → **branch-protection** → Run workflow → leave default
(`main`) → Run.

Verify it succeeded; the job logs should print the required-status-check
count (currently 9 in the repository manifest).

### 4. Verify in Settings

Settings → Branches → `main` → see:

- Require a pull request before merging ✅
- Required approvals: **0** ✅
- Require review from Code Owners: **disabled** ✅
- Require status checks to pass before merging ✅
- 9 status checks listed after the current workflow has been applied
- Require branches to be up to date before merging ✅
- Require conversation resolution before merging ✅
- Require linear history ✅
- Include administrators ✅
- Do not allow force pushes ✅
- Do not allow deletions ✅

## Required status checks (must match CI job names exactly)

| Workflow | Job name |
|---|---|
| ci.yml | `required checks` |
| ci.yml | `CI dependency selection` |
| ci.yml | `task-contract` |
| ci.yml | `gitleaks` |
| ci.yml | `shellcheck` |
| ci.yml | `python validators` |
| ci.yml | `pytest unit tests` |
| codeql.yml | `codeql (python)` |
| codeql.yml | `codeql (actions)` |

If you rename a CI job, update both the matrix in this workflow and the
`CONTEXTS` list in `branch-protection.yml`. Otherwise GitHub treats the
old name as a "missing" required check and the merge is blocked
indefinitely.

The aggregate `required checks` depends on every CI job, including the
`CI dependency selection` planner. It checks the complete named result map
against that planner: selected jobs must succeed, and only explicitly unselected
jobs may be skipped. Missing jobs, failed selection, malformed plans, failures,
cancellations and unexpected skips reject the merge.

PRs select complete consumer groups from the changed-file dependency graph.
Main pushes and manual CI runs execute every group. Unknown paths, shared
configuration, unavailable history and empty diffs also request the full graph.
See [Testing: CI dependency selection](TESTING.md#ci-dependency-selection).

The optional matrix contexts are enforced through the aggregate, not as separate
branch requirements: a skipped matrix does not emit each expanded job name.
After the full PR CI passes, migrate the live context list to the nine names
above **before merging**, preserving strict mode, app bindings and unrelated
settings. Leaving old matrix contexts required would block selective PRs.

`python validators` still executes all seven validators. Pytest, static lint and
task contracts are unconditional. The reusable `tf-policy`, `image-scan`,
`contract-sync` and `reproducible-build` workflows remain in the result gate and
must succeed whenever selected. Their manual entry points remain available;
contract-sync retains its weekly external-drift check.

This gates the outcomes those workflows currently implement. In particular,
`reproducible-build` still permits placeholder example pins and treats Xray
rebuild mismatches as advisory; making it required does not strengthen that
separate verification contract.

## Admin enforcement

The workflow sets `enforce_admins: true`. This is deliberate: this repo deploys
active VPN infrastructure, so maintainers cannot bypass required CI, the pull
request boundary, linear history, or conversation resolution on `main`. The
solo maintainer can merge a green, resolved pull request without an impossible
self-approval. If a second maintainer joins, raise the approval count and
re-enable Code Owner review in the codified workflow before relying on reviews
as a gate. Emergency production repair should still use a short-lived PR with
the same checks, not a direct push around branch protection.

## Why not just enable it in Settings?

You can. The workflow exists so the rule is **codified** — the next
operator checking out the repo sees what protection is meant to be
applied without having to read the org admin's mind. Re-running the
workflow reasserts the rule, which is useful after CI matrix changes.

## Re-running after a CI matrix change

1. Update the CI jobs, `CONTEXTS` in `.github/workflows/branch-protection.yml`,
   and the table above together.
2. Push the PR branch and wait for its new jobs and `required checks` to pass.
   Removed context names can still block merging at this point.
3. **Before merging**, apply the reviewed context migration to `main` through
   the `required_status_checks` API endpoint. Preserve strict mode, GitHub
   Actions app bindings, and every unrelated protection setting.
4. Read back protection and confirm the exact contexts and unchanged settings.
   Confirm the PR's required checks pass, then merge.

Do not wait for a green `main` run to migrate renamed checks: the old names
would prevent that revision from reaching `main`. Use the full
**branch-protection** workflow for initial setup or deliberate reconciliation
of the complete codified rule.

## Informational (NOT required)

These run but don't gate merge:

- `markdown-link-check` (lychee)
- `scorecard` (OSSF)
- `release-please` (writes the release PR; isn't a check)

Adding them to required would block on transient external service
failures (link rot, OSSF rate limits) and slow merges without quality
benefit.
