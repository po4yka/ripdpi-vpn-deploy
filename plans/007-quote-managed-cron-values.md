# Plan 007: Quote and validate every managed cron value

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- scripts/install-operator-crons.sh scripts/CLAUDE.md tests/unit/test_install_operator_crons.py`
> If either existing in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`scripts/install-operator-crons.sh` writes repository paths and operator-controlled environment values directly into executable crontab lines. Spaces break commands, while shell metacharacters in provider, environment, warm-spare, or payload-host values can become commands executed as the crontab owner. The script already computes quoted forms for only one job; the fix is to validate typed identifiers and consistently serialize every executable value for both Bash and cron parsing.

## Current state

- `scripts/install-operator-crons.sh:30-36` reads `PROVIDER`, `ENV`, `WARM_SPARE_ENV`, `PAYLOAD_THROTTLE_HOST`, `REALITY_TARGET_VANTAGE`, and `LIVENESS_CONFIG` from the environment.
- Lines 49-54 validate only `REALITY_TARGET_VANTAGE`.
- Lines 59-63 compute quoted `repo_q`, `env_q`, and `vantage_q`:

```bash
make_block() {
  local repo="$1" repo_q env_q vantage_q
  printf -v repo_q '%q' "$repo"
  printf -v env_q '%q' "$ENV"
  printf -v vantage_q '%q' "$REALITY_TARGET_VANTAGE"
```

- The main jobs at lines 69-74 nevertheless interpolate raw values:

```cron
*/30 * * * *   cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} make burn-check
@daily         cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} make asn-drift
```

- The optional jobs at lines 76-96 interpolate raw `WARM_SPARE_ENV` and `PAYLOAD_THROTTLE_HOST`; only `LIVENESS_CONFIG` and the REALITY monitor line use `%q` output.
- Cron treats unescaped `%` specially even inside shell quotes, splitting the command and sending the remainder to stdin. A correct helper must escape `%` after producing shell-safe text.
- `%q` is Bash syntax for some inputs, so the managed block must explicitly set `SHELL=/bin/bash`; do not rely on the platform's default cron shell.
- The file header claims a macOS launchd plist path, but the implementation has only crontab read/write logic. Correct the stale claim; adding launchd is out of scope.
- `tests/unit/test_monitor_reality_target.py:425-451` is the only existing cron-installer coverage and checks only that the optional REALITY line appears. Create a dedicated hermetic test file instead of expanding the unrelated monitor suite.
- `scripts/terraform-env.sh:17-27` is the canonical provider/environment validation pattern: providers are `upcloud`, `hetzner`, or `vultr`, and environments match `^[A-Za-z0-9][A-Za-z0-9-]*$`.
- Repository shell conventions require `set -euo pipefail`, `printf '%q'` when values will be reparsed by a nested shell, Bash syntax checks, and warning-level ShellCheck.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Bash syntax | `bash -n scripts/install-operator-crons.sh` | exit 0 |
| Focused ShellCheck | `shellcheck -s bash -S warning scripts/install-operator-crons.sh` | exit 0, no warnings |
| Focused regression | `mise exec -- python3 -m pytest tests/unit/test_install_operator_crons.py tests/unit/test_monitor_reality_target.py -q` | all pass |
| Repository shell gate | `mise exec -- make shellcheck` | all managed shell scripts pass |
| Diff hygiene | `git diff --check` | exit 0, no output |
| Commit-scoped secret scan | after commit, `mise exec -- gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- `scripts/install-operator-crons.sh`
- `scripts/CLAUDE.md`
- `tests/unit/test_install_operator_crons.py` (new)

**Out of scope** (do not modify):

- Any watcher/probe script, Makefile target, documentation page, workflow, launchd plist/agent, or scheduler abstraction.
- Changing schedules, job order, logger tags, redirections, enabled/disabled conditions, marker text, remove/install semantics, or the REALITY filtered-vantage policy.
- Executing `eval`, generating an intermediate executable script, or weakening validation to preserve malformed values.
- Supporting new provider names, new environment grammar, URL paths, credentials, or secrets.
- Tests outside the one new focused test file; the existing REALITY monitor test is a regression gate but must not be edited.

## Git workflow

- Branch: `codex/advisor-007-quote-managed-crons`
- Create one focused Conventional Commit: `fix(scripts): quote managed cron values`.
- Do not push, merge, or open a pull request.

## Steps

### Step 1: Validate typed identifiers before rendering

Before marker/block generation in `install-operator-crons.sh`, validate:

- `PROVIDER` is exactly one of `upcloud`, `hetzner`, or `vultr`.
- `ENV` matches `^[A-Za-z0-9][A-Za-z0-9-]*$`.
- Non-empty `WARM_SPARE_ENV` matches the same environment pattern.
- Non-empty `PAYLOAD_THROTTLE_HOST` is either a DNS/IPv4-style host matching `^[A-Za-z0-9][A-Za-z0-9.-]*$` or a bracketed IPv6 literal containing only hexadecimal digits, colons, and dots. Reject whitespace, command separators, substitutions, slashes, and option-like leading hyphens.
- Preserve the existing `REALITY_TARGET_VANTAGE` validation exactly.

Diagnostics must name the invalid variable and exit 2 before checking `LIVENESS_CONFIG`, reading/writing crontab, or printing a managed block. Do not silently normalize identifiers.

**Verify**: `bash -n scripts/install-operator-crons.sh && shellcheck -s bash -S warning scripts/install-operator-crons.sh` → both pass.

### Step 2: Centralize Bash-plus-cron quoting and use it everywhere

Add one helper that accepts a value, obtains Bash-safe serialization with `printf -v ... '%q'`, escapes every `%` for cron after shell quoting, and prints the result without a trailing newline. The helper must not use `eval`. Document the two parsing layers: cron consumes unescaped `%`, then `/bin/bash` parses the command.

Inside `make_block`, compute quoted forms for `repo`, `PROVIDER`, `ENV`, `WARM_SPARE_ENV`, `PAYLOAD_THROTTLE_HOST`, `REALITY_TARGET_VANTAGE`, and `LIVENESS_CONFIG` when applicable. Use the quoted forms in every executable command line, including the base six jobs and all optional jobs. No executable line may interpolate `${repo}`, `${PROVIDER}`, `${ENV}`, `${WARM_SPARE_ENV}`, `${PAYLOAD_THROTTLE_HOST}`, or an unquoted config path directly.

Immediately after the begin marker, emit `SHELL=/bin/bash` within the managed block so `%q` output has a defined parser. Keep the human-readable comment safe by using the already validated provider/environment values. Preserve existing spacing only where practical; behavior and schedules matter more than column alignment.

Correct the header to say the script manages crontab on supported operator systems; remove the unimplemented launchd-plist claim without adding launchd behavior.

**Verify**: run the new focused pytest file → generated commands execute under Bash with the expected argv/environment and no injected command.

### Step 3: Add hermetic command-generation and injection regressions

Create `tests/unit/test_install_operator_crons.py`. Copy the installer into a temporary repository directory whose name contains spaces and `%`, preserving the expected `scripts/` layout so `REPO_ROOT` resolves to that path. Run only `--dry-run`; never write the user's crontab.

Cover at least:

1. Base block: contains `SHELL=/bin/bash`; every base command uses the serialized repository/provider/environment values; the repository `%` is escaped for cron.
2. Command execution: extract one standard five-field cron command after the schedule, execute it with `/bin/bash -c` against stub `make` and `logger`, and assert the stub sees one repository working directory, exact `PROVIDER`/`ENV`, and the expected Make target.
3. Optional warm-spare command: a `LIVENESS_CONFIG` file path containing spaces and `%` remains one exact environment value when the extracted command is executed; `GREEN_ENV` is exact.
4. Optional payload-host command: a valid host reaches `make` as one exact `HOST=...` argument.
5. Injection rejection: parameterize invalid provider, environment, warm-spare environment, and payload host values containing semicolons, whitespace, command substitution, or leading option syntax. Assert exit 2, no managed block on stdout, and no marker file or stub command execution.
6. Existing filtered-vantage behavior: a valid technical label is quoted and rendered; invalid/unfiltered remains rejected as before.

Use executable stub files and captured logs, not string assertions alone, for argv/environment preservation. Avoid asserting the absolute temporary path byte-for-byte where platform temp prefixes differ; derive expectations from `tmp_path`.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_install_operator_crons.py tests/unit/test_monitor_reality_target.py -q` → all new and existing tests pass.

### Step 4: Record the durable script invariant and commit

Add one concise, non-hard-wrapped pitfall or design-decision line to `scripts/CLAUDE.md`: managed cron commands cross both cron and Bash parsers, so validate typed identifiers, serialize every value centrally, escape `%`, and set the shell explicitly. Do not reflow unrelated text.

Run Bash syntax, focused ShellCheck, focused pytest, `make shellcheck`, and `git diff --check`. Confirm exactly the three in-scope files changed. Commit normally with hooks enabled using `fix(scripts): quote managed cron values`; never use `--no-verify` or a skip variable. Run the commit-scoped gitleaks scan and confirm the worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the three in-scope files and `git status --short` has no output.

## Test plan

- Dry-run is the generation boundary; no test may invoke live crontab mutation.
- At least one generated base command and the warm-spare command must be executed through Bash with stubs so quoting is behaviorally proven.
- Invalid identifier tests must prove both rejection and absence of side effects.
- Include a `%` in a valid filesystem/config path to lock cron-layer escaping independently from shell-layer quoting.
- Keep the existing REALITY monitor cron test green for backward compatibility.

## Done criteria

- [ ] Provider, environment, warm-spare environment, and payload host validation rejects command-bearing or malformed values before rendering.
- [ ] One quoting helper handles Bash serialization plus cron `%` escaping without `eval`.
- [ ] The managed block explicitly sets `SHELL=/bin/bash`.
- [ ] Every executable interpolation uses a quoted form; no raw operator value remains in a cron command.
- [ ] Repository and liveness paths containing spaces and `%` survive as exact single values when generated commands execute.
- [ ] Injection attempts produce exit 2 and no command/marker side effect.
- [ ] Focused pytest, Bash syntax, focused ShellCheck, full repository shellcheck, diff hygiene, and commit-scoped gitleaks pass.
- [ ] Exactly three in-scope files are committed; the worktree is clean; the executor reports the commit SHA.

## STOP conditions

Stop and report instead of improvising if:

- Either existing in-scope file drifted from `7bdba37`.
- Cron on a supported platform does not honor an in-block `SHELL=/bin/bash` assignment or treats escaped `%` differently from the stated contract.
- A valid checked-in/documented provider, environment, warm-spare, or payload-host example falls outside the specified grammar.
- Correct generation requires adding launchd support, changing a Make target, or editing an out-of-scope consumer.
- Meaningful command execution tests cannot remain hermetic and avoid live crontab writes.
- Any verification or normal commit hook fails twice after a reasonable in-scope correction.
- The implementation requires modifying a fourth file.

## Maintenance notes

Cron command text has two parsers: cron processes `%`, then the configured shell parses quoting and assignments. Any future optional job must validate typed identifiers, pass every dynamic value through the central helper, and add an execution-level regression; copying a visually quoted line is not sufficient.
