# Plan 011: Pin normal Rust CI to the repository toolchain

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- mise.toml .github/workflows/_rust.yml .github/workflows/mutants.yml tests/unit/test_vpnd_msrv_contract.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED
- **Depends on**: none
- **Category**: migration
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

Local development claims to use the exact Rust version used by CI, but `mise.toml` pins Rust 1.96.0 while the normal reusable workflow and weekly mutation workflow install floating `stable`. A new stable release can therefore change compiler behavior, lints, build artifacts, or cargo-install compatibility without a repository diff, and local checks can disagree with CI. Normal CI must use the repository pin while the explicitly separate Rust 1.88.0 MSRV job remains unchanged.

## Current state

- `mise.toml:1-4` states that `mise install` provisions the exact versions CI uses and that pins must stay synchronized.
- `mise.toml:26-29` currently pins the normal developer toolchain but describes its workflow counterpart as floating stable:

```toml
# dtolnay/rust-toolchain stable; rust-version in vpnd/Cargo.toml remains the
# declared crate MSRV floor, but the current lockfile includes dependencies
# whose manifests require modern Cargo support for Rust 2024 metadata.
rust = "1.96.0"
```

- `.github/workflows/_rust.yml:41-45` is the reusable normal Rust job used by CI and release workflows. It installs `stable` for native tests, clippy, cross-compilation, and release builds:

```yaml
- name: Install Rust toolchain
  uses: dtolnay/rust-toolchain@fa04a1451ff1842e2626ccb99004d0195b455a88  # stable
  with:
    toolchain: stable
    targets: ${{ inputs.target }}
```

- `.github/workflows/mutants.yml:25-28` independently installs the same floating toolchain before installing and running cargo-mutants:

```yaml
- name: Install Rust toolchain
  uses: dtolnay/rust-toolchain@fa04a1451ff1842e2626ccb99004d0195b455a88  # stable
  with:
    toolchain: stable
```

- `.github/workflows/ci.yml:341-356` intentionally installs `toolchain: "1.88.0"` and runs `cargo +1.88.0 check --locked` as the declared MSRV gate. This is not drift and must not change.
- `vpnd/Cargo.toml:5` declares `rust-version = "1.88"`; preserve it.
- `tests/unit/test_vpnd_msrv_contract.py` already proves the Cargo MSRV and CI check agree. Extend its single existing test to cover the normal pin too, rather than adding a second test and forcing unrelated collected-count documentation churn.
- Repository conventions: workflow actions stay SHA-pinned with human-readable version comments; workflow YAML uses quoted dotted toolchain versions; `actionlint` is the syntax/semantic gate; Rust commands use `--locked`; Conventional Commits drive releases.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Focused contract test | `mise exec -- python3 -m pytest tests/unit/test_vpnd_msrv_contract.py -q` | one test passes |
| Workflow lint | `mise exec -- actionlint .github/workflows/_rust.yml .github/workflows/mutants.yml` | exit 0, no diagnostics |
| Rust check on the pinned normal toolchain | `mise exec -- cargo +1.96.0 check --manifest-path vpnd/Cargo.toml --locked` | exit 0 |
| Declared MSRV check | `mise exec -- cargo +1.88.0 check --manifest-path vpnd/Cargo.toml --locked` | exit 0 |
| Diff hygiene | `git diff --check` | exit 0, no output |
| Commit-scoped secret scan | after commit, `mise exec -- gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- `mise.toml`
- `.github/workflows/_rust.yml`
- `.github/workflows/mutants.yml`
- `tests/unit/test_vpnd_msrv_contract.py`

**Out of scope** (do not modify):

- `.github/workflows/ci.yml` and its Rust 1.88.0 MSRV install/check.
- Any caller of `_rust.yml`, including release targets, cargo commands, targets, cache keys, cross behavior, artifact names, permissions, runners, triggers, schedules, issue reporting, or mutation-test policy.
- The SHA pin for `dtolnay/rust-toolchain`, other action SHAs/comments, or any GitHub Action version.
- `vpnd/Cargo.toml`, `vpnd/Cargo.lock`, dependency versions, `rust-version`, Cargo features, source code, tests, clippy settings, cargo-deny policy, or release artifacts.
- Installing/updating Rust, rustup defaults, a `rust-toolchain.toml` migration, changing the MSRV, or updating the normal pin beyond the existing `mise.toml` value.
- Documentation counts, `docs/TESTING.md`, Makefile, CONTRIBUTING, CLAUDE files, CHANGELOG, or unrelated tests/workflows.

## Git workflow

- Branch: `codex/advisor-011-pin-normal-rust-toolchain`
- Create one focused Conventional Commit: `fix(ci): pin normal rust toolchain`.
- Stage exactly the four in-scope files.
- Do not push, merge, cherry-pick, or open a pull request.

## Steps

### Step 1: Pin both normal workflow installs to 1.96.0

In `_rust.yml` and `mutants.yml`, replace `toolchain: stable` with `toolchain: "1.96.0"`. Update only the adjacent `dtolnay/rust-toolchain` comment from `# stable` to `# 1.96.0` so the human-readable comment matches the input. Do not change the action SHA, targets, caches, cargo commands, or any other workflow line.

In `mise.toml`, update the Rust comment to state that the normal `_rust.yml` and `mutants.yml` installs are pinned to 1.96.0. Preserve `rust = "1.96.0"` and the explanation that `vpnd/Cargo.toml` remains the MSRV floor.

**Verify**: `rg -n 'toolchain: stable|# stable' .github/workflows/_rust.yml .github/workflows/mutants.yml` → no output; `rg -n 'toolchain: "1\.96\.0"|# 1\.96\.0' .github/workflows/_rust.yml .github/workflows/mutants.yml` → two matching toolchain lines and two matching comments.

### Step 2: Extend the existing parity contract without adding a test

In `tests/unit/test_vpnd_msrv_contract.py`, keep one test function but rename it to reflect both contracts, for example `test_ci_checks_msrv_and_pins_normal_rust_toolchain`. Add stdlib `tomllib` parsing of `mise.toml` and read `_rust.yml` plus `mutants.yml`.

The test must assert:

1. The existing `rust-version = "1.88"` declaration and `cargo +1.88.0 check --locked` CI command remain present.
2. The `mise.toml` normal Rust value is a string matching an exact three-component numeric version; do not hardcode a second independent version constant in the test.
3. Both normal workflow files contain `toolchain: "<value read from mise>"` and the matching `# <value>` comment.
4. Neither normal workflow contains `toolchain: stable` or a `# stable` toolchain comment.
5. Across `.github/workflows`, the only `toolchain:` value different from the normal pin is the intentional quoted `1.88.0` in `ci.yml`. Implement this narrowly enough not to mistake unrelated prose containing the word `stable` for a toolchain input.

Use only stdlib modules and direct file reads; no YAML parser, GitHub API, subprocess, network, or shell invocation in the test. Keep the suite's collected-test count unchanged by modifying the existing function rather than adding another `test_*` function.

**Verify**: focused contract test → exactly one test passes.

### Step 3: Verify both toolchain roles and workflow syntax

Run actionlint on the two changed workflows. Then run Cargo check explicitly with the pinned normal version and explicitly with the declared MSRV. Both commands must include `--locked`; do not let Cargo update the lockfile. If the `+1.96.0` or `+1.88.0` toolchain is not installed, report that exact environment limitation rather than installing it or silently substituting the default toolchain.

Inspect `git status --short` after both checks and confirm no Cargo manifest, lockfile, source, generated artifact, or workflow outside scope is modified. Ignored `target/` output is permitted in the isolated worktree.

**Verify**: actionlint and both Cargo commands from the command table exit 0; tracked status contains only the four planned files.

### Step 4: Commit the validated slice normally

Run `git diff --check`, inspect the entire diff, and confirm it changes only two workflow toolchain inputs/comments, the matching mise comment, and the existing contract test. Commit normally with hooks enabled using `fix(ci): pin normal rust toolchain`; never use `--no-verify` or a skip variable. After commit, run the commit-scoped gitleaks scan and confirm the isolated worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly `.github/workflows/_rust.yml`, `.github/workflows/mutants.yml`, `mise.toml`, and `tests/unit/test_vpnd_msrv_contract.py`; `git status --short` has no output; scoped gitleaks exits 0.

## Test plan

- The existing single pytest contract continues proving the declared 1.88 MSRV is exercised by CI.
- The same test parses the normal Rust pin from `mise.toml` and compares both independent normal workflow installs against it, preventing local/CI drift without duplicating the version in Python.
- A workflow-wide check permits exactly two toolchain roles: the normal repository pin and the explicit MSRV pin.
- Negative assertions prevent a future return to floating `stable` in either normal workflow.
- Actionlint validates the changed reusable and scheduled workflows.
- Cargo checks prove the committed dependency graph compiles under both the normal and minimum supported toolchains without lockfile mutation.

## Done criteria

- [ ] `_rust.yml` and `mutants.yml` both install quoted Rust `1.96.0` with matching comments and contain no floating stable toolchain input/comment.
- [ ] `mise.toml` remains the normal-toolchain source of truth and documents both workflow consumers.
- [ ] The existing MSRV remains `1.88`/`1.88.0` in Cargo and CI.
- [ ] The single focused contract test extracts the mise pin, checks both normal workflows, permits only the explicit MSRV exception, and passes without increasing test count.
- [ ] Actionlint passes for both workflows.
- [ ] Cargo check passes with `+1.96.0 --locked` and `+1.88.0 --locked`, or an unavailable preinstalled toolchain is reported honestly without installation/substitution.
- [ ] `git diff --check` and commit-scoped gitleaks pass.
- [ ] Exactly four in-scope files are committed; the executor reports the commit SHA; the isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any existing in-scope file drifted from `7bdba37` or no longer matches the excerpts.
- `mise.toml` no longer pins one exact normal Rust version, or another normal Rust workflow install exists outside the two named workflows.
- Pinning 1.96.0 breaks a workflow input, cross target, cargo-mutants installation, release build contract, or requires a newer toolchain/dependency update.
- The MSRV job or `vpnd/Cargo.toml` must change to make normal CI pass.
- Validation requires editing a caller workflow, cache, lockfile, Cargo manifest, action SHA, third workflow, or fifth file.
- The contract test cannot distinguish normal and MSRV toolchains without a YAML dependency, network access, or subprocess.
- Actionlint, focused pytest, a normal commit hook, or a Cargo check fails twice after one reasonable in-scope correction.
- A required toolchain is unavailable and the only way forward is installing it; report the limitation instead of mutating the toolchain environment.

## Maintenance notes

`mise.toml` is the source of truth for the normal Rust version; `_rust.yml` and `mutants.yml` are explicit consumers because GitHub workflow expressions cannot read TOML directly. A future normal-toolchain bump must update those three locations in one commit and pass both the normal and MSRV checks. The 1.88.0 MSRV is a distinct compatibility contract and must never be mechanically replaced with the normal pin.
