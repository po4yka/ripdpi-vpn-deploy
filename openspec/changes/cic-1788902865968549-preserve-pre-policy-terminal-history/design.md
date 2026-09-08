## Context

`CIC-1788708456909496` reached `done` before the repository required a
committed `review` snapshot. The later validator correctly protects new
closures but currently applies that rule to the older transition. A policy bit
read only from the terminal commit would solve the legacy case while allowing a
descendant commit to downgrade the bit and bypass review.

## Goals / Non-Goals

- Goal: bind committed-review enforcement to monotonic activation in the exact
  terminal revision's first-parent config ancestry.
- Goal: make the existing pre-activation High record purgeable without changing
  its historical evidence or terminal receipt.
- Non-goal: relax current close preparation, transition, archive, evidence, or
  deletion validation.
- Non-goal: change runtime, provider, fleet, secret, or deployment behavior.

## Decisions

- Add optional integer `committed_review_policy` to the project config. Preserve
  omission as an unversioned state; the current repository sets version 1.
- Determine enforcement by scanning project-config revisions on the terminal
  commit's first-parent ancestry and treating any observed version 1 as
  permanent activation. A later version 0 or omission therefore cannot disable
  review enforcement.
- Use the same helper in prospective purge resolution and committed deletion
  validation. This keeps the two public validation paths consistent.
- Permit the legacy `doing -> done` form only when the current checkout's
  explicit version 1 proves the terminal revision predates local activation.
  A wholly unversioned peer remains strict, and `todo`, `blocked`, or missing
  source states remain invalid before activation.
- Retain existing transition checks for dropped tasks.

## Contracts and ownership

- `tools/tasking/project.json` owns current policy activation.
- `scripts/tasks/taskctl.py` owns config parsing and historical enforcement.
- `scripts/tests/test_taskctl.py` owns pre-activation compatibility and
  post-activation downgrade regressions.
- The task contract documentation and OpenSpec delta describe operator-visible
  lifecycle semantics. No Terraform, Ansible, `vpnd`, or secrets contract is
  affected.

## Risks / Trade-offs

- Additional Git history reads during terminal validation increase runtime.
  Limit the scan to config-changing commits on the terminal revision's
  first-parent ancestry and reuse the caller's historical-config cache.
- Legacy compatibility is safe only when later local activation proves the
  contract boundary. Unversioned-peer and invalid-source regressions prevent
  omission or policy zero from becoming a general bypass.
- Side-lane terminal commits inherit activation only when it exists in their
  first-parent ancestry, matching the contract actually available on that lane.

## Migration Plan

Set version 1 in the current project config, run focused and full task-contract
tests, then prove the real High purge with base-aware validation. Protected PR
checks, code review, and security review gate integration. Rollback before
integration is a branch revert; after activation, retain version 1 and revert
only the validator implementation if a proven regression requires it.
