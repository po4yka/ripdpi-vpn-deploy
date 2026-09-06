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
count (currently 30 in the repository manifest).

### 4. Verify in Settings

Settings → Branches → `main` → see:

- Require a pull request before merging ✅
- Required approvals: **0** ✅
- Require review from Code Owners: **disabled** ✅
- Require status checks to pass before merging ✅
- 30 status checks listed after the current workflow has been applied
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
| ci.yml | `task-contract` |
| ci.yml | `gitleaks` |
| ci.yml | `terraform fmt + validate (upcloud)` |
| ci.yml | `terraform fmt + validate (hetzner)` |
| ci.yml | `terraform fmt + validate (vultr)` |
| ci.yml | `cloud-init schema` |
| ci.yml | `ansible-lint + syntax-check` |
| ci.yml | `molecule (baseline)` |
| ci.yml | `molecule (firewall)` |
| ci.yml | `molecule (xray)` |
| ci.yml | `molecule (hysteria)` |
| ci.yml | `molecule (nginx-xhttp)` |
| ci.yml | `molecule (watchdog)` |
| ci.yml | `molecule (monitoring)` |
| ci.yml | `molecule (backup)` |
| ci.yml | `molecule (subscription-host)` |
| ci.yml | `shellcheck` |
| ci.yml | `python validators` |
| ci.yml | `pytest unit tests` |
| ci.yml | `terraform test (upcloud)` |
| ci.yml | `terraform test (hetzner)` |
| ci.yml | `terraform test (vultr)` |
| ci.yml | `molecule failure (watchdog)` |
| codeql.yml | `codeql (python)` |
| codeql.yml | `codeql (actions)` |

If you rename a CI job, update both the matrix in this workflow and the
`CONTEXTS` list in `branch-protection.yml`. Otherwise GitHub treats the
old name as a "missing" required check and the merge is blocked
indefinitely.

The aggregate `required checks` context is the forward-compatible gate: it
depends on the complete current CI graph, including Scaleway and newer test
jobs. The remaining individual contexts continue to gate their named checks. If Settings shows fewer than 26 contexts, the remote rule
is stale; rerun `branch-protection` after this documentation commit is green.

`python validators` combines yamllint, secrets coverage, template/Xray checks,
snapshot comparison, and secrets/bundle schema checks. Migrate their five former
required contexts to this context only after the combined job passes; retain
the strict `required checks` aggregate and all unrelated protection settings.

The aggregate also requires the reusable `tf-policy`, `image-scan`,
`contract-sync` and `reproducible-build` workflows. Main CI invokes all four
on every PR, main push and manual CI run, without path filters or duplicate
standalone PR runs. A failure, cancellation or skipped workflow makes
`required checks` fail. Manual workflow entry points remain available;
contract-sync also retains its weekly external-drift check. This extends the
existing required context without changing repository protection settings.

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

1. Update `CONTEXTS` in `.github/workflows/branch-protection.yml`.
2. Update the table above.
3. Push.
4. After CI is green on `main`, run the **branch-protection** workflow.

## Informational (NOT required)

These run but don't gate merge:

- `markdown-link-check` (lychee)
- `scorecard` (OSSF)
- `release-please` (writes the release PR; isn't a check)

Adding them to required would block on transient external service
failures (link rot, OSSF rate limits) and slow merges without quality
benefit.
