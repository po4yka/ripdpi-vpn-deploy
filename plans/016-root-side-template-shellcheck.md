# Plan 016: Shellcheck rendered root-side shell templates

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 15267007..HEAD -- scripts/check-templates-render.py Makefile`
> Re-read the cited regions if they changed since `15267007`.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: assurance
- **Planned at**: commit `15267007`, 2026-09-09

## Why this matters

`ansible/roles/*/templates/` holds 51 `.j2` templates. Several render into
shell that runs as root on nodes: `vpn-sub-mirror.sh.j2`, service
`ExecStart` snippets, watchdog probe wrappers. `make shellcheck` covers
literal `scripts/*.sh` and `terraform/exception/*/*.sh` only. Jinja-level
shell bugs — an unquoted expansion inside a shell word, a `set -e`
interaction introduced by a template conditional — pass yamllint,
ansible-lint, and the render check, then fail (or misbehave) only on a live
node. Finding from the 2026-08-23 audit (OPS-1787495860232652).

## Current state

- `scripts/check-templates-render.py` already renders every template with
  synthetic vars (`template_render.render_template`) and syntax-checks the
  nginx and Xray outputs; rendered shell output is not linted today.
- `make shellcheck`: `shellcheck -s bash -S warning scripts/*.sh
  terraform/exception/*/*.sh`.
- ci-fast runs the render check; the new stage rides the same gate.

## Implementation

1. Extend `scripts/check-templates-render.py`: after a successful render,
   classify the artifact as shell when the template name ends in `.sh.j2` or
   the rendered text starts with a `#!/bin/sh`-style shebang; write it to a
   temp file and run `shellcheck -s bash -S warning` on it.
2. Skip systemd unit files explicitly (unit syntax, not shell), even when
   they embed shell lines; print the skip so the classification stays
   visible.
3. Fail the gate on findings; print the role, template name, and the
   shellcheck report.
4. Fix any findings this raises on current templates as part of this plan —
   the gate must land green.

## Verification

- `python3 scripts/check-templates-render.py` — green with the new stage.
- Detection probe: run the script against a scratch copy of one rendered
  shell template with an injected `rm -rf "$UNSET_VAR"`-class finding → the
  gate must fail.
- `make ci-fast` — green.

## STOP conditions

- A finding inside a systemd unit's embedded shell needs unit-level context
  to judge → scope that one template out with a justified inline skip, never
  a blanket disable.
- Rendering requires new synthetic vars for a template to classify as shell →
  add them; do not bypass the classifier.
