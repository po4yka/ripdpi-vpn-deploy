## Context

See `proposal.md` and W1's archived design in `openspec/changes/archive/2026-11-22-ops-1795327950629406-private-ops-repository-w1/design.md`, which remains the design record for the ops repository, the kit mapping and the merge gate.

## Goals / Non-Goals

- Goal: the capability spec reaches `openspec/specs` through a task that can close.
- Goal: dry-run evidence for W1's deploy-controller change.
- Non-goal: new implementation; the workflow-token refusal stays with `REQ-CIID-MERGE-GATE` (W4).

## Decisions

- Carry W1's spec unchanged instead of re-deriving it, so the requirement set and IDs stay the same.
- Dry-run target: one production node (`node-c`, `ENV=p2-vultr`) in check mode, with the public checkout's ignored `.fleet.mk` including the ops checkout's `fleet.mk`; compare the controller's host selection and resolved input paths with the kit run. Staging is not applicable: W1 changes input paths only and production inputs are byte-identical to the kit.
- Never transfer evidence into or out of this task; every category is decided at creation.

## Contracts and ownership

- `openspec/changes/ops-1795351496232576-private-ops-repository-evidence-w1b/**` and the task file. No code paths.

## Risks / Trade-offs

- A check-mode dry-run touches a production host over SSH → read-only Ansible check mode through the canonical controller, with the operator's authorization at run time.

## Migration Plan

1. Record evidence for the carried spec from pull requests 683 and 686 and the ops repository.
2. With authorization, run the dry-run and record the comparison.
3. Archive with spec sync.

## Open verification questions

1. Does the canonical dry-run need the per-node runner inputs (SSH contexts, promotion configs, extra vars) that the ops repository does not import yet? If so, the dry-run uses them from the kit and records which inputs still come from the kit.
