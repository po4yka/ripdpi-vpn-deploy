# Plan 018: Single source for pinned tool versions

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 15267007..HEAD -- .github/workflows/ci.yml mise.toml Makefile`
> Re-read the cited regions if they changed since `15267007`.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tooling consistency
- **Planned at**: commit `15267007`, 2026-09-09

## Why this matters

Pinned tool versions live in duplicated literals. `terraform_version:
"1.15.2"` appears four times in `.github/workflows/ci.yml` (~lines 176, 202,
511, 578). `PROMTOOL_VERSION` is asserted in the Makefile and pinned in
`mise.toml`. The Xray binary is pinned through a SOPS secret and asserted by
`scripts/check-xray-breaking-changes.py` — that one is deliberate. A bump
that edits one copy desynchronizes CI from local (mise) expectations, and the
desync shows up as a version-mismatch failure in an unrelated job. Finding
from the 2026-08-23 audit (OPS-1787495860232652).

## Current state

- `ci.yml`: `terraform_version` literal at ~lines 176, 202, 511, 578.
- `Makefile`: `PROMTOOL_VERSION` guard in ci-fast; `mise.toml` pins the same
  tool family for local environments.
- Deliberate multi-layer pins: Xray (SOPS secret + guard script),
  AmneziaWG arm64 floor (`check-amneziawg-arm64-version-floor.py`).

## Implementation

1. Introduce `.github/tool-versions.env` as the single literal source for
   `terraform_version`; all four ci.yml jobs read `TF_VERSION` from it.
2. Add `scripts/check-tool-versions.py` (pattern: extend the
   `check-ansible-galaxy-updates.py` drift-check approach) that compares
   `.github/tool-versions.env` against `mise.toml` tool pins; wire it into
   ci-fast.
3. Header-comment the env file: which tools are single-sourced, and which are
   deliberately pinned in multiple layers (Xray, AmneziaWG) with links to
   their guard scripts.

## Verification

- `python3 scripts/check-tool-versions.py` — green; edit-one-copy probe
  (bump only the env file or only mise.toml) fails it.
- All ci.yml jobs resolve `TF_VERSION` from the env file (grep proves zero
  remaining literals).

## STOP conditions

- A workflow needs a deliberately different version from mise → document the
  exception in the env file header and exclude that tool from the drift
  check.
