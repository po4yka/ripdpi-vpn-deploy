# Plan 013: Remove external knowledge-store identifiers from the repository

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- docs/CONTROL-ASSUMPTIONS-AUDIT.md CONTRIBUTING.md docs/TESTING.md docs/PROVIDER-NOTES.md docs/TRANSPORT-REACHABILITY-MATRIX.md docs/CDN-DECISION.md docs/MULTI-COHORT.md ansible/group_vars/all.yml scripts/burn-check.sh scripts/probe-sni-survival.sh scripts/scan-reality-targets.sh scripts/transport-reachability-matrix.sh scripts/validate-reality-target.sh tests/unit/test_repository_identifier_policy.py`
> If any existing in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: docs
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

The root policy forbids names, paths, page slugs, and externally hosted authority references from external knowledge stores, yet a checked-in audit is organized entirely around one such store and several live docs/scripts still cite its concept slugs. Those identifiers make repository decisions impossible to reconstruct from git alone and directly contradict the agent contract. Preserve the useful technical observations as repository-local evidence, remove the external authority framing everywhere it leaked, and make the existing policy test reject the same patterns in future commits.

## Current state

- `CLAUDE.md:22-25` and the root `AGENTS.md` hard rule require all load-bearing knowledge to live in the repository and prohibit external store names, filesystem paths, page slugs, and external citations.
- The deleted 92-line authority-framed audit used an external verdict taxonomy and concept identifiers throughout. Its durable repository-local value was narrower: evidence that single-pass audits overclaim, plus six systemic assumptions that need fail-loud checks.
- `docs/TESTING.md:210-212` and `docs/PROVIDER-NOTES.md:35-40` attribute the provider-edge UDP observation to an external source even though both documents already contain the complete technical reasoning and repository-local probe chain.
- `CONTRIBUTING.md:119` sends contributors to an external rationale pointer for the no-container data-plane decision instead of stating the checked-in architectural boundary.
- `docs/CDN-DECISION.md:99-100` tells readers to revisit a cited external authority page rather than rerun the repository's own measurement/evidence process.
- `docs/TRANSPORT-REACHABILITY-MATRIX.md:90-106`, `scripts/probe-sni-survival.sh:4-18`, `scripts/transport-reachability-matrix.sh:79-84`, and `scripts/validate-reality-target.sh:267-277` already explain the exact-vs-suffix SNI behavior completely but append the same external page slug.
- `scripts/scan-reality-targets.sh:45-48` and `scripts/validate-reality-target.sh:221-225` cite another external page slug for the duplicated over-template/ASN heuristics even though repository-local ownership is `docs/PROVIDER-NOTES.md` plus the validator itself.
- `scripts/burn-check.sh:8-18,159` cites an external concept name in both comments and a runtime warning; the complete ambiguity and tcpdump diagnostic are already in the script and `docs/TESTING.md`.
- `docs/MULTI-COHORT.md:13` and `ansible/group_vars/all.yml:105` cite a page slug for the approximately 12-connection TLS rule; the technical rule itself remains useful and must stay without the slug.
- `tests/unit/test_repository_identifier_policy.py` already excludes itself from scanning, decodes forbidden identifiers from hex, and scans `git ls-files`. Extend this exact policy corpus rather than creating a second scanner. Because it scans the index, stage the exact implementation scope before running it so the deleted/renamed audit is represented accurately.
- Repository convention: documentation conclusions cite checked-in paths and live controls; source comments explain behavior directly; generated snapshots are not involved because only shell comments/diagnostic wording and prose change.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Forbidden-reference scan | `mise exec --no-deps -- python3 -m pytest tests/unit/test_repository_identifier_policy.py -q` | two policy tests pass with no production/doc match |
| Focused policy tests | after staging exact scope, `mise exec --no-deps -- python3 -m pytest tests/unit/test_repository_identifier_policy.py -q` | two tests pass |
| Shell syntax | `bash -n scripts/burn-check.sh scripts/probe-sni-survival.sh scripts/scan-reality-targets.sh scripts/transport-reachability-matrix.sh scripts/validate-reality-target.sh` | exit 0 |
| Shell lint | `shellcheck -s bash -S warning scripts/burn-check.sh scripts/probe-sni-survival.sh scripts/scan-reality-targets.sh scripts/transport-reachability-matrix.sh scripts/validate-reality-target.sh` | exit 0, no diagnostics |
| Full unit regression | `mise exec --no-deps -- python3 -m pytest tests/unit/ -q` | all unit tests pass with unchanged collection count |
| Diff hygiene | `git diff --check --cached` | exit 0, no output |
| Commit-scoped secret scan | after commit, `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- The legacy authority-framed audit (delete)
- `docs/CONTROL-ASSUMPTIONS-AUDIT.md` (new)
- `CONTRIBUTING.md`
- `docs/TESTING.md`
- `docs/PROVIDER-NOTES.md`
- `docs/TRANSPORT-REACHABILITY-MATRIX.md`
- `docs/CDN-DECISION.md`
- `docs/MULTI-COHORT.md`
- `ansible/group_vars/all.yml`
- `scripts/burn-check.sh`
- `scripts/probe-sni-survival.sh`
- `scripts/scan-reality-targets.sh`
- `scripts/transport-reachability-matrix.sh`
- `scripts/validate-reality-target.sh`
- `tests/unit/test_repository_identifier_policy.py`

**Out of scope** (do not modify):

- Any executable branch, thresholds, probe payload, regex, provider/ASN table, cohort value, Ansible variable, firewall rule, transport behavior, exit code, or generated snapshot. Only comments, prose, and the external-slug portion of the burn-check warning may change.
- Re-validating or implementing the historical audit's control findings; Plan 013 preserves durable assumptions, not stale status claims. Do not touch watchdog, subscription-host, firewall, WARP, backup, monitoring, geodata, Xray, nginx, or other roles.
- Adding new external sources, URLs, citations, store aliases, concept identifiers, or paraphrased pointers that still require an unavailable external page.
- Renaming any file except the audit replacement, changing README navigation, or adding the new audit to an operator-critical path.
- Editing root policy wording, AGENTS.md, CLAUDE.md, CHANGELOG.md, plans, task notes, tests other than the existing policy corpus, or any file outside the fifteen listed paths.
- Reflowing unrelated prose or changing measurement claims beyond removing their external attribution.

## Git workflow

- Branch: `codex/advisor-013-remove-external-knowledge-identifiers`
- Create one focused Conventional Commit: `docs(governance): remove external knowledge identifiers`.
- Stage all fifteen paths before policy testing so `git ls-files` observes the audit deletion/addition.
- Do not push, merge, cherry-pick, or open a pull request.

## Steps

### Step 1: Replace the external-authority audit with a repository-native assumptions audit

Delete the legacy authority-framed audit and create `docs/CONTROL-ASSUMPTIONS-AUDIT.md`. Do not mechanically copy the old tables or any external identifier. The replacement must be self-contained and concise, with these sections:

1. **Purpose and status** — dated repository-local review of control assumptions; explicitly a historical evidence snapshot, not a current defect tracker or external compliance report.
2. **Method** — inspect live roles/scripts/config, classify only against checked-in contracts, adversarially cross-check apparent contradictions, and treat unverified observations as investigation candidates.
3. **Durable lessons** — preserve the six useful generalized findings using only checked-in evidence:
   - log-string/schema contracts need fail-loud drift detection;
   - on-host liveness cannot prove filtered-path reachability;
   - single-vantage measurements cannot establish cohort-specific behavior;
   - hardcoded ASN/policy tables are operator judgment and need dated review;
   - early post-deploy exposure needs explicit measurement rather than inferred coverage;
   - single-pass audits overclaim when deployment scope and evidence confidence are not cross-checked.
4. **Repository evidence map** — link each lesson to existing checked-in controls/docs such as `policy-ratelimit`, `burn-check.sh`, `probe-sni-survival.sh`, `TRANSPORT-REACHABILITY-MATRIX.md`, `PROVIDER-NOTES.md`, and relevant role-local CLAUDE files. Use only paths verified to exist.
5. **Maintenance rule** — current status lives beside the owning control/tests; future audits cite repository paths and dated measurement files, never an external knowledge store.

Do not preserve MATCHES/CONTRADICTS/NO-COVERAGE counts, old concept columns, obsolete remediation status, or claims that cannot be supported by a checked-in path. This avoids turning a stale 2026 snapshot into current authority while retaining its review methodology and systemic lessons.

**Verify**: `test -s docs/CONTROL-ASSUMPTIONS-AUDIT.md` and the focused repository-identifier policy tests both succeed.

### Step 2: Remove leaked authority language while preserving complete technical reasoning

Make narrow prose/comment changes:

- `docs/TESTING.md` and `docs/PROVIDER-NOTES.md`: state the provider-edge UDP observation directly as a repository-local deployment/transport assumption; retain the external-probe/tcpdump diagnostic and all current thresholds.
- `CONTRIBUTING.md`: replace the external rationale pointer with a checked-in architectural statement: containers/orchestrators are excluded from the data plane because nodes are disposable and runtime state belongs to Ansible/systemd. Do not invent a new doc link if no single existing section owns the rationale.
- `docs/CDN-DECISION.md`: replace the external-authority revisit instruction with rerunning and recording repository-local filtered-vantage measurements before reversing the decision.
- `docs/TRANSPORT-REACHABILITY-MATRIX.md` and the three SNI-related script comment blocks: remove the page slug/authority preamble, retain the exact-vs-suffix behavior, filtered-vantage requirement, and repository doc/script references.
- `scripts/scan-reality-targets.sh` and step 8 of `validate-reality-target.sh`: state that the over-template and ASN heuristics are repository-owned and must stay synchronized with the validator/`PROVIDER-NOTES.md`.
- `scripts/burn-check.sh`: remove the external concept name from comments and warning output; retain the exact edge-drop ambiguity, non-fatal behavior, and tcpdump next step. The runtime warning must remain equally actionable.
- `docs/MULTI-COHORT.md` and `ansible/group_vars/all.yml`: retain the approximately 12-connection rule and remove only the external slug attribution.

Do not change any command, conditional, regex value, threshold, environment variable, or data structure.

**Verify**: forbidden-reference scan from the command table → no production/doc matches.

### Step 3: Strengthen the existing policy corpus

Extend `tests/unit/test_repository_identifier_policy.py` without adding a test function. Keep the existing hex-encoded corpus approach so the scanner does not self-report. Add encoded exact phrases covering the removed authority leaks: the old audit filename stem, the external-rationale marker, two generic authority phrases, the revisit instruction, and four leaked technical page identifiers.

Also add one compiled case-insensitive regex that detects a lowercase multi-token page slug ending in a four-digit year, for example three or more hyphen-separated tokens ending in `-20NN`. Apply it to scanned tracked content alongside the decoded exact identifiers and report offenders with path plus matched pattern. The policy test file remains excluded by `_should_scan`, and encrypted fixture exclusions remain unchanged.

Do not broadly ban `KB` alone because the repository legitimately uses kilobyte units. Do not ban normal checked-in filenames, dated measurement filenames, semantic versions, or ordinary hyphenated technical terms without a year suffix.

Stage the exact scope before running the test so the deleted old audit is absent from `git ls-files` and the new audit is included.

**Verify**: focused policy tests → two tests pass and the legacy authority-framed audit is absent from tracked files.

### Step 4: Run regressions and commit normally

Run shell syntax/lint, the focused policy tests, and full unit suite. Run the forbidden scan once more, inspect the complete staged diff, and confirm source changes are comments/diagnostic attribution only. Run `git diff --check --cached`.

Commit normally with hooks enabled using `docs(governance): remove external knowledge identifiers`; never skip hooks. After commit, run the commit-scoped gitleaks scan and confirm the isolated worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the fifteen in-scope paths including the delete/add pair; scoped gitleaks exits 0; `git status --short` is empty.

## Test plan

- The existing policy corpus continues protecting carrier/geography restrictions and adds exact external-authority phrases plus a conservative dated-page-slug pattern.
- Staging before the policy test proves the old audit is genuinely removed from the future commit, not merely absent from the worktree view.
- The replacement audit is reviewed as self-contained repository evidence, not validated by the external source it replaces.
- Bash syntax and ShellCheck prove comment/diagnostic edits did not damage five executable scripts.
- Full unit regression covers repository identifier policy, governance counts, probe contracts, and all existing behavior without adding tests or changing documented counts.

## Done criteria

- [ ] The old authority-framed audit is deleted and replaced by a concise repository-native assumptions audit containing the six durable lessons and checked-in evidence map.
- [ ] No production/doc file contains the removed external store language or leaked page slugs.
- [ ] Technical claims, thresholds, filtered-vantage requirements, diagnostics, and runtime behavior remain unchanged except the burn-check warning's attribution wording.
- [ ] The existing repository identifier policy rejects exact authority phrases and conservative dated page slugs without banning kilobyte units or normal dated measurement filenames.
- [ ] Focused policy tests, full unit suite, Bash syntax, and ShellCheck pass.
- [ ] Forbidden scan and `git diff --check --cached` produce no actionable output.
- [ ] Exactly fifteen in-scope paths are committed; the executor reports the commit SHA; the isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any existing in-scope file drifted from `7bdba37` or no longer matches the excerpts.
- A removed external identifier is required by a live executable interface, generated contract, public API, external integration, or filename referenced outside the old audit.
- Preserving a technical conclusion requires importing/citing the external page rather than pointing to checked-in code, tests, or measurement instructions.
- The new regex flags legitimate repository-owned dated measurement filenames or other widespread false positives that cannot be narrowed within the existing policy test.
- A script change would alter behavior beyond diagnostic attribution or requires snapshot updates.
- The old audit is linked from an out-of-scope file or its rename requires updating navigation outside scope.
- Focused/full tests, Bash syntax, ShellCheck, hooks, or forbidden scan fail twice after one reasonable in-scope correction.
- Any sixteenth file, generated artifact, external URL, network lookup, secret, or dependency change is required.

## Maintenance notes

Repository-local evidence is the authority boundary. Future control reviews should record dated observations under `docs/measurements/`, cite the owning source/test paths, and keep current status beside each control. The identifier-policy corpus is intentionally conservative: exact known phrases plus dated page-slug shapes, not a ban on ordinary technical vocabulary or kilobyte units.
