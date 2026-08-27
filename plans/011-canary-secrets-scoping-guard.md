# Plan 011: Refuse canary deploys scoped to non-canary secrets documents

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- Makefile`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug (deploy-safety scoping)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

`.fleet.mk` is included BEFORE the `SECRETS_FILE ?=` / `SOPS_FILE ?=` defaults in the Makefile, so fleet-wide values pinned there silently win over anything the `deploy-canary` target derives from `ENV=canary`. An operator following the README-documented `.fleet.mk` pattern runs `make deploy-canary` and the pre-deploy gates validate the PROD secrets document while the deploy targets canary hosts — wrong-environment blast radius with zero warnings. This guard turns that mismatch into a loud refusal.

## Current state

- `Makefile` head (verified excerpt):

  ```make
  PROVIDER ?= upcloud
  ENV      ?= prod

  -include .fleet.mk
  …
  SECRETS_FILE  ?= $(RUNTIME_DIR)/vpn-$(ENV).secrets.yaml
  SOPS_FILE     ?= $(HOME)/.config/vpn-provision/$(ENV).secrets.sops.yaml
  ```

- `deploy-canary` (~line 252):

  ```make
  deploy-canary:
  	$(MAKE) ENV=canary deploy
  ```

  The recursive `$(MAKE) ENV=canary deploy` re-scopes ENV-derived defaults but CANNOT rescope an explicit `.fleet.mk` value (`?=` never overrides an already-set variable).
- README documents setting `SECRETS_FILE`/`SOPS_FILE` in `.fleet.mk` as the fleet-wide pattern.
- House style for guards: fail-closed one-liners with a clear stderr message and exit 2 (`backup-tf-state.sh` ENV check; Makefile `@command -v … || { echo "missing: …" >&2; exit 1; }`).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Dry parse of new recipe | `make -n deploy-canary` with canary-consistent override | prints recursion line, no error |
| Refusal proof | `make deploy-canary SECRETS_FILE=/tmp/vpn-prod.secrets.yaml` | exit 2, refusal message, nothing deploys |
| Full gate sanity | `make -n check >/dev/null && echo ok` | `ok` (Makefile still parses) |

## Scope

**In scope**:
- `Makefile` — `deploy-canary` recipe only

**Out of scope**:
- `.fleet.mk` itself (operator-local, gitignored — never create/modify one for testing; the command line can simulate pins).
- `deploy` target internals; `ENV=staging` semantics.
- Any change to default variable definitions.

## Git workflow

- Branch: `advisor/011-canary-secrets-guard`
- Commit: `fix(deploy): refuse canary deploys scoped to non-canary secrets files`

## Steps

### Step 1: Add the scoping guard to deploy-canary

The implementation validates canonical basenames rather than the substring
`canary`: `/tmp/canary/vpn-prod.secrets.yaml` must still be refused. It exports
the resolved paths into the recipe environment so quoting in a path cannot
become shell code. Accepted basenames are `vpn-canary.secrets.yaml` and
`canary.secrets.sops.yaml`; both must match before recursive deploy.

See `Makefile` for the canonical recipe and
`tests/unit/test_make_strict_gates.py` for executable pass/refusal cases using
an isolated child-command seam. These tests do not contact infrastructure.

**Verify**: `make -n check >/dev/null && echo ok` → `ok` (recipe parses; `-n` does not execute guards).

### Step 2: Prove the refusal fires on a prod-scoped pin (simulated .fleet.mk via CLI override — equivalent precedence for this test)

```bash
make deploy-canary SECRETS_FILE=/tmp/vpn-prod.secrets.yaml SOPS_FILE="$HOME/.config/vpn-provision/prod.secrets.sops.yaml"; echo "exit=$?"
```

Expected: refusal message for SECRETS_FILE, `exit=2`, NO recursion into deploy (no terraform/ansible output whatsoever).

### Step 3: Prove the guard passes for canary-scoped values WITHOUT deploying

`-n` prints the recipe's shell lines but does NOT execute them — except the guard must be seen to pass. Use `-n` to confirm the recursion line is reached (guard is `@`-prefixed and would still have run under real execution; to prove pass/fail of the guard logic itself without deploying, run the guard expression standalone):

```bash
make -n deploy-canary SECRETS_FILE=/tmp/vpn-canary.secrets.yaml SOPS_FILE="$HOME/.config/vpn-provision/canary.secrets.sops.yaml" | tail -1
```

Expected: last printed line is the `$(MAKE) ENV=canary deploy` recursion (guard did not trigger). Additionally paste the first `if` block into `bash -c` with canary values to watch it fall through (exit 0 path).

### Step 4: Confirm default (no-pin) behavior is unchanged for real canary users

With no overrides, `SECRETS_FILE` resolves at parse time from `ENV=prod` → `vpn-prod.secrets.yaml` → the guard now REFUSES plain `make deploy-canary`. This is the intended behavior change: the operator must scope explicitly. Document it in the commit body. If the maintainer prefers auto-derivation instead of refusal, that is a STOP-and-discuss outcome — do not implement auto-derivation unilaterally.

## Test plan

Command-matrix verification only (Makefile plumbing; no unit-test layer applies). Steps 2–3 are the regression net; keep their exact commands in the PR description.

## Done criteria

- [ ] `make -n check` parses clean
- [ ] Prod-scoped override → exit 2 refusal, zero deploy side effects
- [ ] Canary-scoped override → guard passes, recursion line printed under `-n`
- [ ] Only `Makefile` modified; `plans/README.md` row updated

## STOP conditions

- The Makefile head drifted so `.fleet.mk` is included AFTER the `?=` defaults (the premise is gone — report; the guard would be harmless but pointless).
- `deploy-canary` gains other callers/recipes concurrently — report before rebasing the guard.
- Maintainer feedback prefers warning-only or auto-derivation — stop and re-plan.

## Maintenance notes

- When a staging target appears, it needs the same guard pattern — note it in the recipe comment.
- Reviewers: double-check the `case` inside `if !` quoting under `make` (dollar-doubling) — a malformed guard that always passes is worse than none.
