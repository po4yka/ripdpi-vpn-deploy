# Plan 015: Cover blue-green and fleet-rotate happy paths with stubs

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 15267007..HEAD -- scripts/blue-green.sh scripts/fleet-rotate.sh`
> Re-read both scripts if they changed since `15267007`.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MEDIUM
- **Depends on**: none
- **Category**: assurance
- **Planned at**: commit `15267007`, 2026-09-09

## Why this matters

`scripts/fleet-rotate.sh` (176 lines) and `scripts/blue-green.sh` (194 lines)
drive destructive provider operations. fleet-rotate keeps resumable JSON state
under `.omc/state/fleet-rotate-<id>.json`, enforces a minimum healthy-host
floor, and gates every rotation behind an approval prompt. blue-green is
operator-driven with confirmation pivots and a `--dry-run` plan mode. Both are
exercised only by hand. A regression in plan parsing, state resume, or gate
enforcement surfaces mid-rotation on live infrastructure — the worst possible
time. Finding from the 2026-08-23 audit (OPS-1787495860232652).

## Current state

- `fleet-rotate.sh`: YAML plan (`id`, `min_active`, `rotations[]` with
  `current`/`new_env`/`new_zone`), `--dry-run` validates the plan only,
  `--resume` reads the state file, approval gate between rotation entries.
- `blue-green.sh`: `BLUE_ENV`/`GREEN_ENV`/`PROVIDER` env contract, `--dry-run`
  prints the plan, confirmation prompts at pivot points; shells out to
  terraform/ansible.
- No bats or python coverage for either script; both pass `make shellcheck`.
- External binaries (`terraform`, `ansible-playbook`, `ssh`) are stub-able via
  PATH shims — the established pattern in this repo.

## Implementation

1. `tests/bats/fleet_rotate.bats` with a fixture plan and PATH stubs:
   - valid plan + `--dry-run` → exit 0, both rotations listed, zero stub calls
     that mutate;
   - malformed YAML plan → exit 1 with a readable message;
   - plan that would violate `min_active` at any point → rejected in
     validation;
   - approval prompt answered "n" → abort before any stub terraform call;
   - `--resume` with a pre-seeded state file → completed entry skipped,
     remaining entry runs.
2. `tests/bats/blue_green.bats`:
   - `--dry-run` prints the plan and performs zero mutating stub calls;
   - confirmation refused → clean exit, no stub mutation calls;
   - happy path with stubs → assert call order (create green, converge, pivot,
     retire).
3. Share stubs through one fixture directory sourced by both suites.

## Verification

- `bats tests/bats/fleet_rotate.bats tests/bats/blue_green.bats` — green.
- `make shellcheck` — green.
- CI `bats shell tests` job — green on the implementing PR.

## STOP conditions

- An orchestrator path reads provider state the stubs cannot fake faithfully
  (live zone listing, provider API paging) → scope that path out and report.
- State-file format changes → re-derive the resume fixture.
