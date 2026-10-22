## Context

The existing Bash fleet commands predate strict inventory inspection and
authenticated protocol liveness. The latter already validates bounded reports,
freshness, runtime pins, exact targets and successful authentication. Reuse
these boundaries rather than build another health protocol.

## Goals / Non-Goals

- Goal: truthful passive status, authenticated survivor admission, and durable
  exact-plan resume through the existing Make and vpnd entry points.
- Non-goal: live deployment, client migration, automatic retirement of blue,
  new protocols, a monitoring service, or changes to credential authority.

## Decisions

- Keep shell operator entry points as thin Python launchers. Existing pinned
  Python/PyYAML handle typed inputs and durable state; no dependency is added.
- Extend `fleet_inspection.select_hosts` with an explicit provider/environment
  selection mode; its default exact-name semantics remain unchanged. Status
  retains `HOSTS` or `PROVIDER:ENV` selection but never queries Terraform.
- Status uses `FLEET_INVENTORY` and `FLEET_KNOWN_HOSTS` (existing generated
  inventory and standard known-hosts paths by default). All local admission
  precedes SSH. Keep categorical output and bounded command execution.
- A local watchdog is healthy only after a successful completed invocation
  within 300 seconds with an active timer; client-path status stays unknown.
- Plan schema version 1 contains `id`, `min_active`, `health` with `config`
  and unique `{current, inventory_alias}` nodes, plus ordered `rotations`.
  Each rotation retains `current`, `new_env` and optional `new_zone`.
  Health may include nonrotating standby nodes. Every rotation source must
  appear in that explicit health mapping. Relative config paths resolve from
  the plan directory. Duplicate YAML mappings and unknown fields refuse.
- Count only fresh positive canonical liveness evidence for every required
  profile of distinct surviving aliases, bound to provider/environment and
  public service address. Exclude the current and completed original targets;
  replacement nodes are not silently adopted as survivors. Recheck after the
  human prompt immediately before external execution.
- Hash the canonical complete plan, including resolved health-config path.
  Do not freeze live liveness bytes forever: each invocation revalidates the
  current target configuration and reports as generations advance.
- Hold a private per-plan descriptor lock through execution. Admit state and
  lock ownership, type and modes; refuse symlinks and legacy documents.
  Synchronize atomic journal updates. Persist in-flight before blue-green,
  completed only after successful child exit and durable publication.
- Preserve all blue-green review prompts. Resume works at completed boundaries;
  an uncertain in-flight action requires operator reconciliation rather than
  assuming either success or safe replay. Non-resume never overwrites progress.

## Contracts and ownership

- Status worker: `scripts/fleet-status.sh`, `scripts/fleet_status.py`, minimal
  `scripts/fleet_inspection.py` extension, and status/inspection unit tests.
- Rotation worker: `scripts/fleet-rotate.sh`, `scripts/fleet_rotation.py`,
  `scripts/fleet_rotation_liveness.py`, rotation unit tests and its Bats tests.
- Primary: Make/vpnd integration, existing cross-area fixtures/tests, operator
  docs, subtree guidance, all task/spec/evidence state, review and Git/PR work.
- Terraform, cloud-init, Ansible runtime, secret schemas and protocol engines
  are unchanged. Shared files are edited only by their named owner.

## Risks / Trade-offs

- Stricter plans require independently healthy spare capacity. Refuse when it
  is unavailable rather than presenting a listening socket as VPN proof.
- Completed original nodes are conservatively excluded; safe automatic green
  adoption belongs to a separate client-pivot lifecycle change.
- Uncertain side effects cannot be rolled back by rewriting local progress.
  Retain in-flight authority and diagnostic state for deliberate reconciliation.
- Pure and isolated subprocess regressions prove controller behavior, not live
  network reachability. Run focused tests, full `make check`, independent
  security review, required PR checks and exact-revision main checks.

## Migration Plan

Update all tracked examples and tests to the versioned plan and explicit health
mapping. Existing unbound journals require a separately reviewed plan after
inspection of actual infrastructure; no automatic conversion or reset exists.
Document the new table and inventory prerequisites for `fleet-status`.
Rollback of source is a reviewed revert; do not downgrade a live journal or
restore the old TCP-only availability decision. No infrastructure rollout is
performed by this source change.
