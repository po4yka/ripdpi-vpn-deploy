# Plan 017: Add an ephemeral-only Path A recovery execution spike

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, do not edit `plans/README.md`; the reviewer maintains the index in the advisory checkout.
>
> **Dependency preparation (run first in the isolated worktree)**: start from commit `7bdba37`, then merge dependency commit `4b772dd` so the original Plan 013 identity remains an ancestor. It must apply cleanly and preserve Plan 013's repository-identifier cleanup in `docs/TESTING.md`. Stop on any conflict.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: 013 (`4b772dd`)
- **Category**: direction
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`scripts/restore.sh` mirrors the recovery runbook but stops after printing dry-run steps; its real mode always exits 1. The repository already has a label-gated ephemeral-VPS workflow, provider-aware environment routing, fail-closed secret checks, and Bats stubs for orchestration. A safe next step is not general production recovery automation. It is a deliberately narrow tracer that can execute deterministic Path A only for an exactly confirmed `ci-*` throwaway environment, while production environments and Path B remain manual. This proves sequencing, failure behavior, and interface shape without granting a broad destructive recovery command or claiming live recovery has been exercised.

## Current state after dependency preparation

- `scripts/restore.sh` is POSIX `/bin/sh`, supports `--path-a`, `--path-b`, and `--dry-run`, validates only path selection and presence of `--env`, and makes no provider/slug validation.
- Its dry-run Path A sequence is: restore secrets, provision, decrypt, dry-run, deploy, verify, clean. Its non-dry branch prints “real mode is not yet automated” and exits 1.
- Path B intentionally restores snapshot contents into `/` and must remain manual until a separate design addresses repository selection, snapshot identity, overwrite scope, and rollback.
- `Makefile` owns every step needed for Path A: `decrypt`, `pre-deploy-check`, `init`, `plan`, `apply`, `inventory`, `wait`, `dry-run`, `deploy`, `verify`, and `clean`. `pre-deploy-check` validates strict secrets, spot-checks values, and checks certificates.
- `scripts/terraform-env.sh` centrally maps `PROVIDER` + `ENV` to a Terraform workspace. Operator scripts must call Makefile/wrapper surfaces rather than raw Terraform.
- `scripts/destroy.sh` establishes the repository's non-interactive safety vocabulary: only validated `ci-[A-Za-z0-9][A-Za-z0-9-]*` environments may bypass human prompts.
- `tests/bats/restore_dryrun.bats` has twelve tests, many of which assert only a substring. It prepends existing command stubs but no tracked `make` stub exists. Rewrite these same twelve test cases to characterize dry-run plus the new execution gates; do not add tests or change the repository's documented 46-Bats count.
- Bats can create a temporary `make` executable in `$BATS_TEST_TMPDIR` for execution tests and prepend that directory to `PATH`. Do not add a tracked global make stub because another existing restore test deliberately invokes real `make -n`.
- `docs/RUNBOOK-restore.md` calls Path A recommended and targets 15–30 minute recovery, but has no executable-spike section or warning that the new mode is throwaway-only.
- `docs/TESTING.md` currently says restore real mode is not implemented/tested and incorrectly references a nonexistent `tests/unit/test_restore_dryrun.py`; the actual coverage is `tests/bats/restore_dryrun.bats`.
- `scripts/CLAUDE.md` requires one script per operator verb, SOPS gates, centralized Terraform routing, fail-loud behavior, and audit logging for destructive operations. Record the new ephemeral-only safety boundary there because it is architecturally novel.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Dependency ancestry | `git merge-base --is-ancestor 4b772dd HEAD` | exit 0 |
| POSIX syntax | `sh -n scripts/restore.sh` | exit 0 |
| Shell lint | `shellcheck -s sh -S warning scripts/restore.sh` | exit 0, no diagnostics |
| Focused restore tests | `mise exec --no-deps -- bats tests/bats/restore_dryrun.bats` | exactly 12 tests pass |
| Full Bats regression | `mise exec --no-deps -- bats tests/bats/` | exactly 46 tests pass |
| Full unit regression | `mise exec --no-deps -- python3 -m pytest tests/unit/ -q` | all unit tests pass with unchanged collection count |
| Forbidden executable paths | `rg -n -- '--execute-ephemeral.*path-b|production execution|prod.*execute|restore latest --target /' scripts/restore.sh` | no new executable Path B/production implementation; inspect any historical dry-run text match |
| Diff hygiene | `git diff --check --cached` | exit 0, no output |
| Commit-scoped secret scan | after commit, `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files the Plan 017 commit may modify relative to the Plan 013 dependency baseline):

- `scripts/restore.sh`
- `tests/bats/restore_dryrun.bats`
- `docs/RUNBOOK-restore.md`
- `docs/TESTING.md`
- `scripts/CLAUDE.md`

**Out of scope** (do not modify):

- `.github/workflows/real-vps-deploy.yml` or any CI workflow. This spike becomes eligible for later workflow integration but does not consume credentials/provider credit in this plan.
- Path B execution, restic repository selection, snapshot overwrite, rollback, destructive cleanup, automatic destroy, production/non-`ci-*` execution, or recovery of an existing environment.
- Terraform, Ansible, Makefile, SOPS, audit-log, destroy, provider, role, template, secret schema, fixture, global stub, generated file, or runtime control changes.
- Creating real infrastructure, decrypting real secrets, contacting a provider, or running the execution mode outside the Bats stub harness during implementation/review.
- Adding a generic `--execute`/`--force`, environment-variable bypass, production escape hatch, interactive prompt, or automatic attempt to continue after a failed step.
- Increasing Bats test count, changing documented counts, adding dependencies, or updating `CHANGELOG.md`/plans/any sixth file.

## Git workflow

- Branch: `codex/advisor-017-ephemeral-recovery-spike`.
- Start from `7bdba37` and merge `4b772dd` with a Conventional Commit merge message before editing; the original dependency SHA must remain an ancestor.
- Create one focused incremental Conventional Commit: `feat(recovery): add ephemeral Path A execution spike`.
- Do not push, merge into the user's branch, or open a pull request.

## Steps

### Step 1: Harden argument validation and keep the default fail-closed

Extend `scripts/restore.sh` while preserving POSIX `/bin/sh`:

- Add `--execute-ephemeral` and `--confirm-env <name>` to usage/argument parsing. Do not add a generic execution flag.
- `--dry-run` and `--execute-ephemeral` are mutually exclusive. With neither flag, retain a fail-closed guidance response and nonzero exit; do not silently turn today's non-dry invocation into execution.
- Validate `PROVIDER` against exactly `upcloud|hetzner|vultr` before either dry-run or execution.
- Validate every `ENV` as a technical slug `^[A-Za-z0-9][A-Za-z0-9-]*$`. Execution additionally requires `ENV` to match `^ci-[A-Za-z0-9][A-Za-z0-9-]*$`.
- Execution requires `--path-a`, rejects `--path-b`, requires a nonempty `--confirm-env`, and requires it to exactly equal `ENV`.
- Error text must identify the failed gate without printing secrets. Use exit 2 for invalid/unsafe execution requests and retain nonzero behavior for all invalid combinations.
- Do not accept an environment-variable bypass. The two explicit CLI tokens plus the `ci-*` restriction are the authority boundary.

Keep dry-run output non-mutating and update it to distinguish the executable ephemeral spike from production recovery. Path B dry-run remains documentation only.

**Verify**: focused tests cover invalid provider/slug, absent/mismatched confirmation, production refusal, mutually exclusive modes, and Path B execution refusal.

### Step 2: Execute the fail-loud Path A sequence only inside the gate

Add a small POSIX function that invokes the make binary as `PROVIDER="$PROVIDER" ENV="$ENV" "$RECOVERY_MAKE" <target>`, where `RECOVERY_MAKE="${RECOVERY_MAKE:-make}"`. This override exists only so Bats can supply a temporary make stub; document it in a comment as test-only and do not expose it as a CLI flag.

After all execution gates pass:

1. Change to `REPO_ROOT` derived from the script path.
2. Run `decrypt`, then `pre-deploy-check` before any infrastructure action. This deliberately fails before provisioning when recovered secrets/certificates are unusable.
3. Run, one target per invocation, `init`, `plan`, `apply`, `inventory`, `wait`, `dry-run`, `deploy`, `verify`, `clean` in that exact order.
4. Print a numbered, secret-free step label before each command.
5. Use `set -eu` to stop immediately. Track whether `apply` completed. Install a POSIX `EXIT`/`0` trap that, on later failure, warns that the ephemeral node may remain for diagnosis and prints the exact operator-owned destroy command `PROVIDER=<provider> ENV=<env> make destroy`; it must never destroy automatically. The trap must preserve the original exit status and be silent on success/pre-apply failure.
6. After `verify` succeeds and before `clean`, append a best-effort audit event through the existing `scripts/audit-log.sh` with action `recovery-path-a-spike`, exact env/provider, and a non-secret note that this was ephemeral execution. Audit failure must not fail recovery.
7. Print a completion message that calls the result an ephemeral Path A spike, not production recovery proof.

Never shell-evaluate a constructed command, never invoke raw Terraform/Ansible, never combine targets in a way that hides which step failed, and never log decrypted paths/values.

**Verify**: the stub log proves exact target order; an injected failure stops before later targets; a post-apply failure emits the preservation warning without a destroy invocation.

### Step 3: Rewrite the existing twelve Bats cases as meaningful characterization

Keep exactly twelve `@test` blocks in `tests/bats/restore_dryrun.bats`. Preserve setup/teardown isolation, then replace redundant substring-only cases with coverage for:

1. Path A dry-run succeeds, identifies env/provider, and leaves `STUB_LOG` empty.
2. Path B dry-run succeeds, retains restic/manual guidance, and leaves `STUB_LOG` empty.
3. Missing env/path and mutually exclusive path flags fail (one test may run multiple invocations).
4. Invalid provider and invalid environment slug fail before commands.
5. Neither `--dry-run` nor `--execute-ephemeral` fails closed.
6. Execution rejects a production-shaped environment.
7. Execution rejects missing and mismatched `--confirm-env`.
8. Execution rejects Path B.
9. Dry-run and execution flags together fail.
10. Successful ephemeral Path A logs exactly `decrypt pre-deploy-check init plan apply inventory wait dry-run deploy verify clean` in order.
11. A stub failure before apply stops immediately with no later target and no preservation warning.
12. A stub failure after apply stops immediately, prints the preservation/manual-destroy warning, and never calls `destroy`.

For execution tests, create a per-test executable at `$BATS_TEST_TMPDIR/bin/make` that appends only its target argument to `STUB_LOG`, optionally exits nonzero when `RECOVERY_STUB_FAIL_TARGET` matches, and otherwise succeeds. Invoke the script with `RECOVERY_MAKE` pointing to that absolute stub. Do not put the stub on global PATH, write outside `BATS_TEST_TMPDIR`, or expose realistic secret material.

Ensure the existing Path B ordering check that protects decrypt-before-playbook is retained in either its dry-run test or an additional assertion within the same twelve cases. Test names should describe behavior rather than numbering.

**Verify**: focused Bats reports `1..12` and all pass; full Bats remains exactly 46.

### Step 4: Document the spike boundary and future promotion gate

Update `docs/RUNBOOK-restore.md` with a concise subsection after Path A:

- Show the exact throwaway-only invocation using placeholders: `scripts/restore.sh --env ci-<technical-id> --provider <provider> --path-a --execute-ephemeral --confirm-env ci-<technical-id>`.
- State prerequisites: prepared environment tfvars, restored age/SOPS material, provider credentials, and normal toolchain.
- State the execution order at a high level and that secrets preflight precedes apply.
- State it refuses production environments and Path B, never auto-destroys, and preserves a post-apply failure for diagnosis/manual destroy.
- State this is stub-verified orchestration only, not a measured 15–30 minute live recovery or authorization to run against production.
- Name the future promotion gate: integrate an explicit recovery-spike input into the existing label/manual ephemeral-VPS workflow and observe successful provision/deploy/verify/destroy across its supported OS matrix before considering broader execution.

Update only the restore bullet in `docs/TESTING.md`: point to `tests/bats/restore_dryrun.bats`; say dry-run and ephemeral execution ordering/safety gates are stub-tested; say no credentialed live recovery spike is run in CI yet and Path B/production remain manual. Preserve Plan 013's repository-native terminology and do not change counts.

Add one compact design decision and one pitfall to `scripts/CLAUDE.md`: execution is ephemeral Path A only with exact confirmation; failures after apply preserve rather than auto-destroy. Keep the three-section format and line budget.

### Step 5: Run regressions and commit normally

Run syntax, ShellCheck, focused/full Bats, and full unit regression. Inspect the complete incremental diff against the dependency baseline and confirm only five in-scope files changed, the script contains no production/Path B execution branch, and no test invokes real make/provider tools.

Stage exactly the five files and run `git diff --check --cached`. Commit normally with hooks enabled using `feat(recovery): add ephemeral Path A execution spike`; never skip hooks. After commit, verify dependency ancestry, exact five-file diff-tree, scoped gitleaks, and a clean worktree.

## Test plan

- Dry-run remains zero-side-effect for both paths.
- Negative Bats cases prove every authority gate fails before the make stub is invoked.
- Successful execution proves secrets preflight precedes all infrastructure and the full Path A order is deterministic.
- Failure injection proves fail-loud behavior before and after apply and prevents accidental automatic cleanup.
- Full Bats preserves adjacent blue-green/fleet/credential orchestration behavior and exact collection count.
- Full unit regression catches governance/documentation drift on the Plan 013 baseline.

## Done criteria

- [ ] Default/no-mode invocation remains fail-closed; only explicit ephemeral mode can execute.
- [ ] Provider/env/path/mode/confirmation gates reject unsafe inputs before commands.
- [ ] Execution is restricted to exactly confirmed `ci-*` Path A environments; Path B and production remain manual.
- [ ] Secrets preflight occurs before init/plan/apply; remaining make targets run in exact documented order.
- [ ] Failures stop immediately; post-apply failure warns and preserves state without calling destroy.
- [ ] Best-effort audit logging records successful spike completion without exposing secrets.
- [ ] Exactly twelve focused restore Bats and 46 full Bats pass; no real infrastructure command runs in tests.
- [ ] Runbook, testing boundary, and scripts knowledge layer accurately label the spike and promotion gate.
- [ ] Syntax, ShellCheck, full unit, hooks, diff hygiene, ancestry, and scoped gitleaks pass.
- [ ] Exactly five Plan 017 files are committed; the executor reports the commit SHA; isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Plan 013 does not merge cleanly or its docs/TESTING identifier cleanup is missing.
- A Makefile target cannot be called independently with inherited `PROVIDER`/`ENV`, secrets preflight requires an already-provisioned node, or a safe Path A order differs materially from this plan.
- Safe failure handling requires automatic destroy, raw Terraform, production execution, Path B restore, real credentials, interactive input, or a workflow/Makefile/third-party change.
- The Bats harness cannot isolate `make` without a tracked global stub or any test reaches a real provider/tool.
- Maintaining exactly twelve restore tests/46 full Bats would sacrifice a named safety gate rather than merely consolidate redundant assertions.
- Focused/full tests, syntax, ShellCheck, hooks, ancestry, or scans fail twice after one reasonable in-scope correction.
- Any sixth file, generated artifact, dependency change, external lookup, real secret/value, carrier/geography identifier, or external knowledge-store reference is required.

## Maintenance notes

This commit proves an orchestration seam, not recovery readiness. Production promotion requires credentialed evidence in the existing ephemeral workflow, measured RTO, explicit cleanup ownership, and a separate decision about whether production confirmation can ever be made safe. Path B remains a distinct, higher-risk design problem because it restores rendered secret-bearing state over a fresh host.
