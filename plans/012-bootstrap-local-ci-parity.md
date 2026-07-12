# Plan 012: Provide one complete local CI-parity bootstrap path

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- Makefile mise.toml docs/QUICKSTART.md docs/TESTING.md CONTRIBUTING.md README.md CLAUDE.md tests/unit/test_make_strict_gates.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

The documented first-time setup checks deployment tools and installs Python hooks, but it does not provision or even report several standalone tools required by `make ci-fast`: actionlint, cloud-init, ShellCheck, Bats, cargo-deny, and Rust 1.88.0. A new contributor can follow every onboarding step and then discover missing tools one gate at a time. The repository needs one non-privileged bootstrap target for portable tools plus one exhaustive parity preflight that reports all remaining platform prerequisites at once.

## Current state

- `docs/QUICKSTART.md:18-23` tells operators to run `make check-prereqs` and `make install-hooks`, implying that setup is complete afterward.
- `Makefile:140-145` checks only `terraform ansible ansible-playbook ansible-lint sops age gitleaks jq ssh python3` plus PyYAML and exits on the first missing item.
- `Makefile:271-274` installs hashed Python requirements and hooks, but no standalone CI tools or Rust MSRV.
- `Makefile:298-359` makes `ci-fast` fail closed on actionlint, cloud-init, Terraform, yamllint, ShellCheck, cargo-deny, Cargo with `+1.88.0`, Python render/schema/unit tooling, Bats, clippy, and Rust tests.
- `mise.toml` currently pins only Terraform 1.15.2, Python 3.12, Rust 1.96.0, and gitleaks 8.30.1. Mise's registry supports actionlint, age, Bats, jq, ShellCheck, and SOPS; its explicit Cargo backend supports installing crates such as cargo-deny with `locked = true`.
- Pin these already-verified versions: actionlint 1.7.12, age 1.3.1, Bats 1.13.0, jq 1.8.2, ShellCheck 0.11.0, SOPS 3.13.2, and cargo-deny 0.19.0. Do not opportunistically upgrade them.
- Cloud-init is intentionally different: CI installs the Ubuntu package with `apt` in `.github/workflows/ci.yml:96-105`; it is not a portable mise tool. On Ubuntu the documented prerequisite is `sudo apt-get install cloud-init`; on macOS the full schema gate must run inside an Ubuntu environment such as the operator's VM/Multipass environment or be left to CI. The preflight must never silently skip it.
- `tests/unit/test_make_strict_gates.py` already asserts that `ci-fast` contains its promised subtargets. Extend its single existing test instead of adding a second test and changing the documented collection count.
- `README.md:230`, `CONTRIBUTING.md:24-44`, `docs/QUICKSTART.md:7-23`, `docs/TESTING.md:103-112`, and `CLAUDE.md:72-80` are the checked-in onboarding/development surfaces that must name the same bootstrap and parity commands.
- Repository convention: Makefile is the canonical operator surface; portable versions live in mise, Python package versions remain in hashed `requirements.txt`, system packages are never installed silently, and new prose paragraphs are not hard-wrapped unless matching surrounding local style.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Mise configuration | `mise install --dry-run` | exit 0 and lists the newly pinned portable tools without installing them |
| Focused contract test | `mise exec --no-deps -- python3 -m pytest tests/unit/test_make_strict_gates.py -q` | exactly one test passes without auto-installing newly declared tools |
| Base prerequisite check | `mise exec --no-deps -- make check-prereqs` | exit 0 on the executor host without dependency preparation |
| Parity prerequisite check | `mise exec --no-deps -- make check-prereqs CI_PARITY=1` | exits nonzero only for genuinely missing tools; on the current macOS host it must name cloud-init explicitly and report the Ubuntu-environment guidance |
| Help surface | `make help` | includes `bootstrap-dev` and the CI_PARITY preflight |
| Full unit regression | `mise exec --no-deps -- python3 -m pytest tests/unit/ -q` | all unit tests pass with the pre-existing collected count and the complete pre-existing tool PATH |
| Diff hygiene | `git diff --check` | exit 0, no output |
| Commit-scoped secret scan | after commit, `mise exec -- gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- `Makefile`
- `mise.toml`
- `docs/QUICKSTART.md`
- `docs/TESTING.md`
- `CONTRIBUTING.md`
- `README.md`
- `CLAUDE.md`
- `tests/unit/test_make_strict_gates.py`

**Out of scope** (do not modify):

- Requirements files, dependency pins other than the seven explicit portable CLI additions, Cargo manifests/lockfiles, Rust normal/MSRV versions, pre-commit hook definitions, CI workflows, action SHAs, Terraform locks, or application/source code.
- Installing any tool while executing this plan. Validate the bootstrap definition with dry-run and contract tests; do not run `make bootstrap-dev`, `mise install` without `--dry-run`, pip install, rustup install, Homebrew, apt, curl installers, or remote scripts.
- Auto-installing cloud-init, Docker, Multipass, Homebrew, apt packages, or any privileged/system package. The repository owns diagnosis and instructions, not workstation package-manager state.
- Weakening, skipping, reordering, or conditionally bypassing any `ci-fast`, `validate`, or `check` gate.
- Changing `install-hooks` semantics except reusing it from the new bootstrap target.
- Windows onboarding, container/devcontainer creation, CI images, or a general package-manager abstraction.
- Editing `AGENTS.md`, `CHANGELOG.md`, docs outside the five named onboarding surfaces, or adding a new test file/function.

## Git workflow

- Branch: `codex/advisor-012-bootstrap-local-ci-parity`
- Create one focused Conventional Commit: `feat(dx): add local parity bootstrap`.
- Stage exactly the eight in-scope files.
- Do not push, merge, cherry-pick, or open a pull request.

## Steps

### Step 1: Make mise own every portable standalone prerequisite

Add exact tool entries to `mise.toml` for:

```toml
actionlint = "1.7.12"
age = "1.3.1"
bats = "1.13.0"
jq = "1.8.2"
shellcheck = "0.11.0"
sops = "3.13.2"
```

Keep existing Terraform, Python, Rust, and gitleaks values unchanged, then place `"cargo:cargo-deny" = { version = "0.19.0", locked = true }` after the existing Rust entry. That ordering is load-bearing because `bootstrap-dev` uses `mise install --jobs=1` and a clean machine must install Cargo before invoking the Cargo backend. Group/comment the file so it states that mise owns portable runtimes/CLIs, hashed requirements own Python packages, Rust 1.88.0 is installed as an additional rustup toolchain by bootstrap, and cloud-init remains a manual Ubuntu package. Do not add `latest`, loose version prefixes, a mise lockfile, or a platform-specific binary URL.

**Verify**: `mise install --dry-run` → exit 0 and mentions every configured tool; `git status --short` contains no mise cache/lock artifact.

### Step 2: Add exhaustive prerequisite reporting and a bootstrap target

Add `bootstrap-dev` to `.PHONY` and Makefile help. Implement it in this order:

1. `mise install --jobs=1` so the Rust runtime exists before the cargo-backed cargo-deny install.
2. `mise exec -- $(MAKE) install-hooks` to reuse hashed Python installation and both existing pre-commit hook installs.
3. `mise exec -- rustup toolchain install 1.88.0 --profile minimal` for the explicit MSRV used by `vpnd-msrv`.
4. `mise exec -- $(MAKE) check-prereqs CI_PARITY=1` as the final proof.

Do not hide output or continue after failure. The target may finish nonzero when cloud-init is unavailable; that is intentional and must point to the documented manual prerequisite.

Refactor `check-prereqs` so it accumulates failures instead of exiting on the first one. Preserve the base deployment tools and add `openssl`, which QUICKSTART already lists. When `CI_PARITY=1`, also require `actionlint`, `cloud-init`, `shellcheck`, `bats`, `cargo-deny`, `cargo`, `yamllint`, and the Python modules used by the local bundle (`yaml`, `jinja2`, `jsonschema`, `pytest`). Run `cargo +1.88.0 --version` to distinguish a present Cargo executable from a missing MSRV toolchain.

For a missing cloud-init executable, print concise platform guidance: Ubuntu/Debian installs the `cloud-init` package; macOS runs the full parity command inside an Ubuntu VM/environment because mise does not own cloud-init. List every missing item before exiting once. A successful base check prints `base prerequisites present`; a successful parity check prints `CI parity prerequisites present`.

Do not add shell-specific arrays, Bash-only syntax, temporary files, eval, network probes, or package installation to the checker; Make recipes run under portable `/bin/sh` semantics.

**Verify**: base prerequisite check succeeds; parity check on the current host fails only for cloud-init and contains `missing: cloud-init` plus the platform guidance.

### Step 3: Lock the bootstrap/preflight contract in the existing test

Extend the single function in `tests/unit/test_make_strict_gates.py`; do not add a test function. Parse `mise.toml` with stdlib `tomllib` and assert the exact portable tool/version map, including the cargo-deny table's version and locked flag. Inspect the Makefile and assert:

- `bootstrap-dev` is phony, visible in help, and executes the four ordered operations above.
- `check-prereqs` contains every base and parity executable, the four required Python imports, and the `cargo +1.88.0 --version` probe.
- The checker accumulates a failure flag and emits cloud-init guidance instead of exiting inside the first tool-loop iteration.
- The existing `ci-fast` target assertions remain unchanged and every standalone executable directly required by its named subtargets is represented in parity prerequisites.
- Neither `ci-fast` nor `check` gains a skip variable or optional-tool branch.

Keep this an offline structural contract. Do not invoke make, mise, package managers, subprocesses, or the network inside pytest.

**Verify**: focused contract test → exactly one test passes.

### Step 4: Align all onboarding and knowledge surfaces

Update the five named prose surfaces consistently:

- `docs/QUICKSTART.md`: list mise and cloud-init accurately, give Ubuntu installation and macOS Ubuntu-environment guidance, replace the misleading two-command setup with `make bootstrap-dev`, then show `make check-prereqs CI_PARITY=1` and `make ci-fast` as proof.
- `CONTRIBUTING.md`: first-time setup uses `make bootstrap-dev`; explain it installs pinned portable tools, hashed Python packages, MSRV, and hooks, while cloud-init must be provided first by the platform guidance. Remove the redundant `make install-hooks` line from local pre-flight.
- `README.md`: replace the one-time `make install-hooks` operator command with `make bootstrap-dev` and a concise purpose comment.
- `docs/TESTING.md`: add `bootstrap-dev` and parity preflight rows before `ci-fast`; state cloud-init is manual/platform-specific and never skipped.
- `CLAUDE.md`: add `make bootstrap-dev` and `make check-prereqs CI_PARITY=1` to Development, with the durable ownership boundary: mise portable tools, requirements Python packages, platform cloud-init.

Preserve deploy instructions, credentials guidance, all gate descriptions, and surrounding formatting. Do not claim macOS can run cloud-init schema natively when it cannot.

**Verify**: `rg -n 'bootstrap-dev|CI_PARITY=1|install-hooks' README.md CONTRIBUTING.md docs/QUICKSTART.md docs/TESTING.md CLAUDE.md` → bootstrap/parity commands appear on all intended surfaces and `install-hooks` remains only where documenting the lower-level target is still intentional.

### Step 5: Run regressions and commit normally

Run the focused test, full unit suite, base checker, and parity checker through `mise exec --no-deps --`; the `--no-deps` flag is mandatory after editing `mise.toml` so verification loads the already-installed Python/Ansible environment without auto-installing the newly declared tools. Run Make help and mise dry-run separately. The parity checker is expected to be nonzero solely because cloud-init is absent on the current macOS host; record that limitation and do not claim the gate is green. Run `git diff --check`, inspect the full eight-file diff, and ensure no lock/cache/generated file is tracked.

Commit normally with hooks enabled using `feat(dx): add local parity bootstrap`; never skip hooks. After commit, run the commit-scoped gitleaks scan and confirm the isolated worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the eight in-scope files; scoped gitleaks exits 0; `git status --short` is empty.

## Test plan

- One existing pytest function guards the complete portable mise pin set and the Makefile bootstrap/checker contract without changing collection counts.
- Mise dry-run validates backend/version resolution without installing or activating tools.
- Base preflight proves deploy prerequisites remain usable independently of contributor-only parity tooling.
- CI parity preflight proves all missing tools are diagnosed together and cloud-init fails explicitly with actionable platform guidance.
- Make help and five documentation surfaces keep onboarding discoverable and consistent.
- Full unit regression catches exact-count, governance, or policy drift caused by onboarding text changes.

## Done criteria

- [ ] Mise pins all seven added portable tools at the specified exact versions; existing pins are unchanged; the Rust entry precedes the cargo-deny backend entry.
- [ ] `bootstrap-dev` installs mise tools serially, reuses hashed Python/hook setup, installs Rust 1.88.0 minimally, and ends with the parity preflight.
- [ ] Base `check-prereqs` preserves deploy checks, adds OpenSSL, reports all missing items, and can succeed without contributor-only tools.
- [ ] `CI_PARITY=1` covers every standalone ci-fast dependency, required Python modules, and the actual Rust 1.88.0 toolchain; it never skips cloud-init.
- [ ] Missing cloud-init produces actionable Ubuntu and macOS/Ubuntu-environment guidance.
- [ ] The existing single strict-gates test meaningfully protects tool versions, bootstrap ordering, exhaustive preflight, and no-skip behavior.
- [ ] README, QUICKSTART, TESTING, CONTRIBUTING, and CLAUDE agree on the bootstrap/parity commands and ownership boundaries.
- [ ] Focused and full unit tests pass; Make help, mise dry-run, and base preflight pass; parity preflight fails only for documented missing cloud-init on the current host.
- [ ] `git diff --check` and commit-scoped gitleaks pass.
- [ ] Exactly eight files are committed; the executor reports the commit SHA; the isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any existing in-scope file drifted from `7bdba37` or no longer matches the excerpts.
- Mise cannot resolve one of the exact tool names/versions in dry-run, or cargo-deny requires a lock/dependency/Rust-version change.
- The portable tool install requires root privileges, remote installer piping, Homebrew/apt mutation, or a new tracked lock/cache file.
- Cloud-init can only be made green by silently skipping it, weakening `ci-fast`, adding Docker/VM implementation, or auto-installing a system package.
- Base deployment preflight would newly require contributor-only tools.
- Bootstrap cannot reuse `install-hooks` without changing its established behavior.
- The checker requires Bash-only syntax or a new script/ninth file.
- Documentation cannot be made accurate without promising unsupported native macOS cloud-init behavior.
- Any focused/full unit test, mise dry-run, normal commit hook, or available-tool preflight fails twice after one reasonable in-scope correction.
- Any dependency version outside the seven named additions or any out-of-scope file must change.

## Maintenance notes

Mise is the source of truth for portable standalone developer tools; `requirements.txt` remains the source for Python packages, and rustup owns the additional MSRV toolchain. Cloud-init is deliberately platform-owned because its schema command ships with the Ubuntu package used by CI. When `ci-fast` adds a new standalone executable, update the mise pins when portable, the CI parity prerequisite list, the strict-gates contract, and onboarding in the same change.
