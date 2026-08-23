# Plan 006: Add the conftest Rego gate to the local union gate

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- Makefile mise.toml .github/workflows/tf-policy.yml`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx (gate parity)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

CI blocks PRs on `conftest verify --rego-version v0 -p terraform/policy/` (job in `.github/workflows/tf-policy.yml`), but neither `make ci-fast` nor `make check` runs any conftest step. A Rego policy edit or a provider change that violates `terraform/policy/` sails through the documented "full local gate" and fails only after push — exactly the green-local-red-CI class the gate exists to prevent, contradicting the Makefile's own comment that missing local tooling must "be a failure rather than a misleading green gate".

## Current state

- `Makefile` — `check:` is `task-check validate ci-fast` (~line 508); the `ci-fast` body (~lines 478–503) contains `@$(MAKE) tf-test` but NO conftest/tf-policy step.
- `Makefile` `tf-test` target (~lines 431–437), verified excerpt:

  ```make
  tf-test:
  	@command -v terraform >/dev/null 2>&1 || { echo "missing: terraform" >&2; exit 1; }
  	@for provider in upcloud hetzner vultr scaleway; do \
  	  echo "== terraform test: $$provider =="; \
  	  terraform -chdir=terraform/providers/$$provider init -backend=false >/dev/null && \
  	  terraform -chdir=terraform/providers/$$provider test || exit 1; \
  	done
  ```

- A separate `tf-policy` target exists near line ~734 re-running the same init+test loop plus conftest — it is NOT referenced by ci-fast/check. Do not wire THAT target (it would double the terraform work); split instead per Steps below.
- `.github/workflows/tf-policy.yml` (~lines 44–51): installs a checksum-pinned conftest binary, then `terraform init -backend=false && terraform test` per matrix provider, then:

  ```yaml
        - name: conftest policy unit tests
          run: conftest verify --rego-version v0 -p terraform/policy/
  ```

  Confirm the exact pinned version from the install step lines above it (~line 40) before Step 3.
- `mise.toml` — toolchain pins with per-entry CI cross-reference comments (exemplar entries: `terraform = "1.15.2"`, `"pipx:zizmor" = "1.29.0"`). Conftest is currently absent.
- Policies live in `terraform/policy/*.rego`; unit tests alongside (`conftest verify` runs them).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Provision tool | `mise install` (after editing mise.toml) | conftest present on PATH via shims |
| New target | `make tf-policy-verify` | exit 0 on current repo |
| Union gate | `make check` | exit 0 end-to-end |
| Policy-only sanity | `conftest verify --rego-version v0 -p terraform/policy/` | exit 0 |

## Scope

**In scope**:
- `Makefile` (one new target + one line in `ci-fast`)
- `mise.toml` (one pin entry + its CI cross-reference comment)
- `docs/TESTING.md` (single parity-table row if such a table lists local checks)

**Out of scope**:
- Any `.rego` policy content; any workflow file (CI already correct).
- Removing/replacing the old `tf-policy` target's terraform half beyond what Step 1 specifies.
- The exception-root validation gap (separate finding).

## Git workflow

- Branch: `advisor/006-conftest-local-gate`
- Commit: `fix(ci-fast): run conftest policy tests in the local union gate`

## Steps

### Step 1: Add a conftest-only target next to tf-test

In the Makefile, directly after the `tf-test` recipe:

```make
tf-policy-verify:
	@command -v conftest >/dev/null 2>&1 || { echo "missing: conftest (see mise.toml)" >&2; exit 1; }
	conftest verify --rego-version v0 -p terraform/policy/
```

Flags mirror the CI job byte-for-byte. Fail-closed tool check matches the house pattern (`tf-test`, `yamllint-check`).

**Verify**: `make tf-policy-verify` → exit 0 (requires conftest installed; proceed to Step 2 first if absent).

### Step 2: Wire into ci-fast

Insert `	@$(MAKE) tf-policy-verify` immediately after the existing `	@$(MAKE) tf-test` line inside the `ci-fast` recipe.

**Verify**: `grep -n "tf-policy-verify" Makefile` → two hits (target + ci-fast call).

### Step 3: Pin conftest in mise.toml

Read the CI install step to get the exact version, then add under `[tools]` following the file's comment convention:

```toml

# conftest: checksum-pinned install in .github/workflows/tf-policy.yml
conftest = "<VERSION-FROM-CI>"
```

Run `mise install`. If your shell lacks mise, document the manual install you used instead in the PR body — do not silently skip.

**Verify**: `command -v conftest && conftest --version` → prints the pinned version.

### Step 4: Prove the gate actually bites

Temporarily append an intentionally-failing assertion to one policy test file under `terraform/policy/` (e.g. duplicate a rule name or assert false), run `make tf-policy-verify` expecting non-zero, then revert the temp change.

**Verify**: failing case exits ≠ 0 with a Rego error; after revert, `make tf-policy-verify` → exit 0 again.

### Step 5: Docs parity touch-up

If `docs/TESTING.md` enumerates what `ci-fast` covers, add/adjust the row for the conftest policy tests so the doc matches reality (the audit found this doc already claims conftest among "PR-blocking CI"; make sure the LOCAL column now agrees).

**Verify**: `grep -n "conftest" docs/TESTING.md` reflects both CI and local coverage.

## Test plan

No unit tests apply (Makefile plumbing); verification is the command matrix above, especially Step 4's positive+negative proof.

## Done criteria

- [ ] `make tf-policy-verify` exits 0 on the clean repo, exits ≠ 0 with a broken policy
- [ ] `make check` passes end-to-end on a machine with tools installed
- [ ] mise.toml pins match the CI-installed version exactly
- [ ] Only in-scope files modified; `plans/README.md` row updated

## STOP conditions

- `make tf-policy-verify` fails on the UNMODIFIED repo (pre-existing policy drift) — report the failure output; do not fix policies here.
- The CI conftest version cannot be determined unambiguously from the workflow — report rather than guessing.
- `make check` reveals unrelated pre-existing failures — note them and stop after confirming they reproduce without your change.

## Maintenance notes

- When someone later touches `terraform/policy/`, `make check` is now sufficient pre-PR signal — update any docs that still say "policy verified only in CI".
- Deferred deliberately: sharing one terraform init between tf-test and the policy job (perf finding, separate plan).
