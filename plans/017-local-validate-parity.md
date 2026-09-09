# Plan 017: Local validate parity — plugin cache, galaxy, prereqs

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 15267007..HEAD -- Makefile .gitignore requirements.yml`
> Re-read the cited regions if they changed since `15267007`.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: developer experience / gate parity
- **Planned at**: commit `15267007`, 2026-09-09

## Why this matters

`make validate` runs `terraform validate` for four provider roots; each root
needs its own init, so local validation pays provider downloads per root.
ansible-lint and the syntax check depend on galaxy collections: repo-root
`requirements.yml` exists and molecule consumes it, but the local validate
path never installs it. `check-prereqs` covers a partial tool list, so a
fresh contributor learns about a missing tool only when a failing target
prints it mid-run. Hosted CI already does all of this; locals re-derive it
badly. Findings from the 2026-08-23 audit (OPS-1787495860232652): local
validate without terraform init, galaxy collections local install,
check-prereqs expansion — one parity bundle.

## Current state

- `Makefile` `validate` (~line 450): fmt-check + validate for upcloud,
  hetzner, vultr, scaleway; gitleaks; ansible-lint; syntax-check.
- `requirements.yml` at repo root; referenced by molecule scenarios only.
- `check-prereqs` (~line 439): terraform version check; ci-fast guards tools
  point-of-use (shellcheck, conftest, ansible-playbook, promtool, cargo,
  bats, …).
- No `TF_PLUGIN_CACHE_DIR` wiring anywhere in the repo.

## Implementation

1. Add `make tf-init-cache`: init all four provider roots with a shared
   `TF_PLUGIN_CACHE_DIR` (default `.terraform-plugin-cache/`, added to
   `.gitignore`).
2. `validate` honors a pre-populated cache; when absent, print a one-line
   hint pointing at `make tf-init-cache`.
3. Add `make galaxy-install` (`ansible-galaxy install -r requirements.yml`).
4. Add `make local-env` bundle: `tf-init-cache` + `galaxy-install`; document
   it in the local-development section of `README.md`.
5. Expand `check-prereqs` to enumerate every tool ci-fast can require —
   terraform, gitleaks, ansible-lint, ansible-playbook, shellcheck, bats,
   conftest, promtool, cargo, cargo-deny, python3 with jinja2, node — each
   with the install hint its target already prints.

## Verification

- Clean cache: `make local-env` once, then `make validate` green with no
  per-root network downloads (cache hits observable in terraform output).
- `make check-prereqs` prints every tool with its version, or exits 1 with
  the matching install hint.
- `.terraform-plugin-cache/` ignored by git.

## STOP conditions

- None expected; all changes are Makefile and docs surface.
