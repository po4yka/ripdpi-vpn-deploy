## Context

`zizmor` 1.29.0 reports 52 default-persona findings when scoped to the
repository-owned `.github/` tree and `.pre-commit-config.yaml`: 27
`artipacked`, 19 `template-injection`, five `dependabot-cooldown`, and one
`superfluous-actions`. Scanning the repository root also collects a vendored
`bats-assert` workflow fixture and therefore is not an acceptable production
scope. The existing `ci.yml` workflow already has a `required` aggregate job,
and `mise.toml` plus the Makefile are the canonical local tool and operator
surfaces.

The repository has one maintainer, but classic branch protection currently
requires one approving CODEOWNERS review while enforcing the rule for admins.
GitHub does not permit self-approval, so a green pull request cannot be merged
by its only maintainer. No repository rulesets are configured. Separately, the
two immutable Molecule image pins now produce fixed HIGH findings in Trivy;
fresh upstream digests are available and scan clean.

The remediation is a repository/CI change only. Terraform roots, cloud-init,
Ansible roles, SOPS+age secrets, `vpnd` runtime behavior, fleet state, and live
deployment paths are unaffected.

## Goals / Non-Goals

- Goal: structurally remove all 52 owned default-persona findings with no
  blanket or rule-level suppressions.
- Goal: provide one exact-version, strict, offline audit command shared by the
  local validation contract and a required CI job.
- Goal: preserve the semantics of builds, releases, dependency delivery, and
  deployment workflows while reducing credential and input-expansion risk.
- Goal: preserve required CI and destructive-history protections while removing
  the impossible approval requirement for the sole maintainer.
- Goal: restore the hosted image-scan gate by refreshing immutable upstream
  image digests instead of suppressing fixed vulnerabilities.
- Non-goal: audit shell or program files indirectly invoked by workflow steps;
  `zizmor` does not model those files.
- Non-goal: gate on vendored or third-party workflow fixtures outside the owned
  input scope.
- Non-goal: redesign release orchestration or add a PAT/GitHub App credential
  so release-please-created tags can trigger a second workflow. That existing
  remote-release limitation requires an explicit credential or orchestration
  decision and is independent of the `zizmor` baseline.
- Non-goal: deploy, mutate secrets, or claim remote CI evidence without a push.

## Decisions

- Pin `pipx:zizmor` 1.29.0 in `mise.toml`. The local Make target checks the
  observed binary version before scanning so an ambient incompatible binary
  cannot silently define the gate.
- Add `zizmor-check` to the Makefile and the portable `ci-fast` bundle. It runs
  with `--offline`, `--strict-collection`, `--no-config`, the regular persona,
  and explicit collection kinds against `.github` and
  `.pre-commit-config.yaml`. `--no-config` prevents an unreviewed repository or
  environment configuration from weakening the required baseline; no finding
  currently requires even an inline suppression.
- Add a dedicated `zizmor` job to `.github/workflows/ci.yml` and make the
  existing `required` aggregate depend on it. A separate workflow/context is
  rejected because it would require an independent branch-protection contract
  and manual protection rollout.
- Run the CI audit offline with `contents: read`, checkout credential
  persistence disabled, and no GitHub token passed to the analyzer. Download
  the exact upstream Linux release archive into runner-temporary storage and
  verify its committed SHA-256 before execution. SARIF is rejected for the
  blocking gate because `zizmor` intentionally exits zero for semantic SARIF
  findings; GitHub annotation output retains fail-closed exit codes.
- Remediate `artipacked` by removing the checkout from the branch-protection
  job that does not use the workspace and setting `persist-credentials: false`
  on every other flagged checkout. Manual review confirmed no affected job
  performs a later authenticated git operation.
- Remediate reusable Rust inputs by carrying values through environment
  variables, validating the target grammar, parsing the command into an array,
  and quoting every target/path expansion. This preserves the current literal
  command contracts without inserting input into shell source.
- Remediate `github.base_ref` by passing it through the environment, validating
  it with `git check-ref-format`, using an explicit quoted fetch refspec, and
  quoting the diff revision.
- Remediate both deployment `zone` inputs by setting `TF_VAR_zone` at the job
  boundary and removing the value from generated heredocs. Terraform's
  existing zone validation remains authoritative and the provider credentials
  are no longer exposed to a shell-expanded dispatch value.
- Remediate reproducible-build pin values by validating version/hash grammar at
  their source, mapping step outputs into environment variables, and quoting
  their uses. Pull-request-controlled repository content never becomes shell
  program text.
- Add a seven-day Dependabot default cooldown to every ecosystem. Security
  updates remain exempt from cooldown; deleting Dependabot is rejected because
  it is the observed active dependency updater.
- Replace the redundant release-upload action with built-in `gh`, using one
  resolved tag for tag and manual-dispatch paths. Create a missing release with
  its complete asset set, preserve existing notes on reruns through `upload
  --clobber`, recover an interrupted draft, and serialize mutations per tag.
- Keep the pull-request protection object but encode zero required approving
  reviews and disable mandatory Code Owner review. Keep strict required status
  checks, admin enforcement, linear history, conversation resolution, and
  force-push/deletion denial. Retain CODEOWNERS as future review routing, but do
  not enforce it while the repository is operated by one maintainer.
- Replace every old Debian 13 and Ubuntu 24.04 Molecule image digest with the
  verified current upstream immutable digest. Do not add Trivy exceptions for
  vulnerabilities already fixed in those images.
- Add focused contract tests for the analyzer pin/flags/scope/required job and
  for each changed workflow contract. Update the governance test count only
  from the final collected suite rather than predicting it.

## Contracts and ownership

- `mise.toml` owns the exact local analyzer version.
- `Makefile:zizmor-check` owns the canonical invocation; `ci-fast` owns local
  portable parity.
- `.github/workflows/ci.yml` owns remote execution and the required aggregate.
- `.github/workflows/*.yml` and `.github/dependabot.yml` own workflow and
  dependency-delivery behavior. No cross-layer interface is introduced.
- `tests/unit/` owns static assertions for version parity, scope, least
  privilege, required-job wiring, and workflow-specific remediations.
- `docs/TESTING.md` owns the operator-facing validation inventory and observed
  test count.
- The primary agent serializes all writes and commits. Parallel sub-agents are
  read-only triage lanes and cannot stage or commit shared files.

## Risks / Trade-offs

- Static-analysis false positives can block CI -> use the regular persona,
  explicit owned scope, and structural fixes; any future exception must be
  rule-specific and source-local with a reviewed safety argument.
- An upstream release asset could be replaced or unavailable -> verify a pinned
  checksum and fail closed; the repository pin is upgraded only with review.
- Adding the audit to `ci-fast` adds a tool prerequisite and runtime -> make the
  missing/wrong version error explicit and keep the scan offline and bounded.
- Command-array parsing may differ from arbitrary shell parsing -> preserve and
  test the current supported literal cargo commands; intentionally stop
  supporting shell metacharacters as part of the reusable-workflow contract.
- `gh release upload --clobber` deletes an existing named asset before upload ->
  this matches current rerun overwrite intent, while a failed upload can require
  a rerun to restore the asset.
- Release-please using the default `GITHUB_TOKEN` may not trigger the tag-based
  asset workflow -> report this pre-existing remote-release blocker separately;
  do not introduce an undocumented high-authority credential in this change.
- Local validation cannot prove required remote CI execution -> retain the task
  in review until a pushed final SHA has observed remote evidence; commits alone
  prove only the local gates requested here.
- A future second maintainer may need mandatory review -> re-enable required
  reviews in the codified payload and documentation as an intentional policy
  change; CODEOWNERS remains available for routing.
- Upstream image tags are mutable even when their digests are not -> commit only
  registry-resolved digests and require the hosted scan before acceptance.

## Migration Plan

1. Commit the validated portfolio task and OpenSpec plan.
2. Commit each remediation lane separately: reusable Rust inputs, base-ref
   handling, deployment zone inputs, reproducible pin values, checkout
   credentials, Dependabot cooldowns, and release upload behavior. Run the
   relevant focused tests and the scoped analyzer after each lane.
3. Commit the exact tool pin, Make target, required CI job, tests, and operator
   documentation together so local/remote version parity cannot land partially.
4. Run the scoped analyzer, actionlint, YAML validation, affected unit tests,
   the full unit suite, `make ci-fast`, `make validate`, `make check`, taskctl
   validation, and final diff inspection.
5. Record observed local evidence. Remote CI remains explicitly unverified
   until the commits are pushed and the required aggregate completes.
6. Commit the solo-maintainer protection contract, update the live classic
   branch protection through the GitHub API, and verify both classic protection
   and rulesets surfaces.
7. Commit the Molecule image digest refresh separately, then require both the
   hosted image-scan matrix and the complete required aggregate to pass on the
   pushed final SHA.

Rollback is commit-oriented: revert the integration commit to remove the gate
and tool prerequisite while keeping the independently safe remediation commits.
Individual remediations can be reverted only if their original security risk is
explicitly accepted; no rollback changes deployed infrastructure or secrets.
