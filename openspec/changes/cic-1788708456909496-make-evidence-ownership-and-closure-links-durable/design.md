## Context

The local portfolio stores active tasks in `docs/tasks/issues/` and removes each
issue only after a committed terminal state and archived execution record.
`taskctl` already reconstructs purged terminal tasks for federation, but local
validation currently requires every local reference to resolve to an active
issue. `close purge` also rejects every incoming relationship. Consequently an
operational owner cannot retain a durable `related_tasks` edge to a completed
source task even though proportional evidence requires that ownership to remain
auditable.

## Goals / Non-Goals

- Goal: preserve non-blocking local evidence-ownership links across canonical
  `done` task purge and expose the resolved historical node in task graphs.
- Goal: reject every historical target that does not prove one unambiguous,
  valid, committed `done` lifecycle.
- Goal: make shared requirement mappings and client-layer evidence explicit in
  the repository closure policy.
- Non-goal: permit a missing parent, unresolved blocker, dropped task, or prose
  pointer to satisfy an active dependency or acceptance requirement.
- Non-goal: close or archive any existing Critical/High task, or relax its
  incomplete evidence to `passed` or `not_applicable` without the required proof.
- Non-goal: change Terraform, Ansible, secrets, providers, deployed hosts,
  clients, or production infrastructure.

## Decisions

- Reuse the terminal-history validator rather than create a second receipt
  format. A historical reference is trustworthy only if the same task issue,
  execution snapshot, archive receipt, close receipt, and transition rules used
  by federation validate successfully.
- Resolve missing local targets only for `related_tasks`. Parentage is structural
  and must remain active; `blocked_by` is an execution gate and must be removed
  or explicitly updated before its target can be purged. This keeps the current
  fail-closed dependency semantics.
- Build one cached local history index per command invocation. Re-scanning the
  complete Git history for each related edge would make validation cost grow by
  tasks multiplied by commits.
- Support the pre-commit purge state explicitly. After `close purge` deletes the
  issue but before the deletion commit, `HEAD` still contains the committed
  terminal snapshot. The resolver may accept that snapshot only when the
  working tree contains the matching archived receipts and the candidate was
  `done`; the subsequent base-aware validation still proves the deletion
  lifecycle.
- Render resolved historical related nodes with `historical: true`, terminal
  status, terminal revision, and deletion revision where available. Do not add
  them to `taskctl list` or `ready`; they are audit context, not open work.
- Store shared operational acceptance as matching structured requirement rows
  in both owning verification records. Each row names requirement ID, command,
  evidence category, and exact source revision. The task relationship points to
  the owner; it does not itself count as evidence.
- Activate historical transfer auditing with the repository project contract's
  `evidence_transfer_policy: 1`. Missing or zero preserves legacy history, while
  the activation commit itself is audited so it cannot hide a reclassification.
- Update the proportional policy to name `client` explicitly for authenticated
  client traffic. Evidence categories remain cumulative when more than one
  layer is applicable.

## Contracts and ownership

- `scripts/tasks/taskctl.py`: local historical-reference index, validation,
  purge rules, and graph projection. No command bypasses terminal validation.
- `tests/unit/test_task_contract*.py`: RED-first cases for valid pre/post-purge
  related edges, dropped and malformed history, ID reincarnation, unsafe parent
  and blocker edges, graph output, and rollback/no-write failures.
- `docs/tasks/README.md`: evidence ownership, client category, and historical
  related-link semantics.
- `docs/tasks/issues/` and active `verification.md` files use the new mapping
  only in a later OpenSpec update that actually transfers an exact requirement.
  This change may record current observations as `blocked` and move a task back
  from `review` to `blocked`; it does not transfer, pass, waive, or close them.
- `openspec/specs/ci/task-contract-validation/spec.md`: synced normative task
  contract after implementation and acceptance.

## Risks / Trade-offs

- Full-history parsing can be expensive. Cache parsed revisions once and resolve
  only missing local related IDs; add a bounded regression that proves multiple
  references do not trigger independent history walks.
- Accepting a working-tree deletion could hide an invalid purge. Require a
  committed terminal `done` snapshot plus matching archived receipts, then keep
  existing base-diff deletion validation unchanged.
- A historical ID can be reintroduced by the existing recovery contract.
  Validate the latest incarnation independently so an earlier valid lifecycle
  cannot mask a later invalid terminal transition.
- A related edge might be mistaken for acceptance. Keep evidence mapping and
  category checks separate; links establish ownership only.
- Existing tools may assume graph nodes are all active. Add `historical` to the
  JSON projection and keep existing active-node fields unchanged; consumers must
  branch on the explicit flag.

## Migration Plan

1. Add failing task-contract tests for valid and invalid historical references,
   safe purge, graph projection, and client evidence policy.
2. Implement cached local history resolution and narrow purge allowance for
   incoming `related_tasks` only.
3. Update the policy text and document the exact ownership-mapping contract.
   Preserve every incomplete acceptance boundary; record observed unavailable
   inputs and failed probes as `blocked` without transferring requirements.
4. Run focused pytest, `./taskctl generate-board`, `./taskctl validate --base
   origin/main`, `make task-check`, and `git diff --check`.
5. Review every published commit message for repository-local rationale and the
   absence of external citations. Continue the existing pull request when its
   history passes that check, and merge only after all protected required checks
   and review threads are satisfied.
6. After exact protected-main checks pass, record that source evidence in this
   task. Existing operational tasks remain blocked until their own dry-run,
   staging, live, and client evidence passes.

Rollback is a normal revert of the source and policy commit before any task uses
historical related links. If a later rollback is required, first restore active
task records or remove/update every historical related edge so validation never
silently loses evidence ownership.
