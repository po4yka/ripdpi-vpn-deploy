# MON-1792080593038468: Deliver isolated resource-bounded monitoring acceptance

## Objective

Accept the working monitoring implementation through real isolated processes and complete source gates, without external infrastructure. Preserve prior unpassed live evidence as cancelled history rather than success.

## Ownership

- Monitoring worker owns the bounded collector scenario, resource tests, role notes and proposal/spec/design.
- Primary owns this execution/verification record, portfolio/board, shared docs, the Kuma CI runtime invocation, commits and publication.
- Recovery worker independently reviews source and observes existing exact-source CI. No worker reverts another lane or contacts live infrastructure.

## Execution

- [x] MON-1792080763077431 Verify bounded sender and collector replay private ingress resource isolation and rollback #feature !high @item:MON-1792080593038468
- [x] MON-1792080764176275 Verify observer push persistence encrypted restore and honest delivery states #feature !high @item:MON-1792080593038468
- [x] MON-1792080765681879 Integrate monitoring contracts and complete isolated runtime and source acceptance #feature !high @item:MON-1792080593038468

## Verification

- Source: focused Mac monitoring tests, `make snapshot-check`, `make task-check`, full-history/staged secret scanning and the complete unchanged exact-SHA hosted source/native checks.
- Runtime: canonical enabled collector/agent Molecule scenarios and pinned Kuma `molecule/runtime/run.py` in the existing role CI job; no selected skips.
- Independent security review, exact-source hosted results and requirement mappings in verification.md.
- Dry-run against real hosts, live deployment, external client performance and human receipt are excluded from creation.

Run focused sender/collector/resource and observer/push/relay tests, scenario lint, snapshots, complete exact-SHA hosted source checks and task/OpenSpec validation. Require exact-revision hosted canonical enabled collector/agent scenarios and pinned observer timing/persistence/isolated restore evidence. Record observed local, hosted and artifact evidence separately. External-host dry-run, staging, live deployment and live client acceptance are not applicable from task creation; they remain future deployment prerequisites. Planning or portable fixtures alone cannot close these steps.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.
