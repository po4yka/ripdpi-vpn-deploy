## Context

See `proposal.md`. Today `--site commit` deletes `site.json` and then `transport_runtime_outer.py finish` closes the egress outer route. Next-run recovery is per journal: ANS-1791996027408136 adopts an open `site.json` into the rescue (ingress restore plus egress rollback when its route is open), and egress `runtime-prepare.yml` recovers an open outer route on its own.

## Goals / Non-Goals

- Goal: no interruption point leaves ingress and egress at different accepted generations.
- Non-goal: a deploy-level lock or a new recovery verb.

## Decisions

- Record a commit marker in one journal before touching the other (for example, the site journal gains a `committing` phase written before egress `finish`, and is removed only after `finish` succeeds). Next-run recovery then finishes a commit that reached the marker and restores both when it did not. The exact marker owner is decided in implementation planning; the rejected alternative is reordering the two steps, which only moves the window.

## Contracts and ownership

- The protected block rescue stays the single compensation owner; the commit marker is read by the same detection as site journal adoption.

## Risks / Trade-offs

- Roll-forward on recovery must reuse the accepted readiness proof, not assume it. Mitigation: SIGKILL tests at every boundary.

## Migration Plan

No node migration; nodes without journals are unaffected. Rollback: revert the change.
