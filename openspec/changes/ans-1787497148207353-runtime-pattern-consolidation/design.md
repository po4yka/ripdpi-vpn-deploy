## Context

Ten duplication clusters and two scaffold hazards, quantified with per-site citations in the linked record. The repo's own conventions (per-role defaults as complete variable surface, fail-closed listener contract) stay intact — this change removes parallel copies, not contracts. SEC-1787496747898735 owns the two zero-hardening inline units; TST-1787497001212692 owns idempotence phases that will back this change's behavior-preservation claims.

## Goals / Non-Goals

- Goal: one implementation per runtime concern, migrated without behavior drift except documented capability gains.
- Non-goal: changing pins, ports, toggles, or any operator-visible default; no new roles beyond the shared install path.

## Decisions

- Shared installer as an internal role consumed via include_role (not a collection): stays inside repo tooling, molecule-testable.
- Migration order: shared path lands first with unit tests; consumers migrate one commit each so any regression bisects to one switch-over.
- Port defaults move to all.yml rather than a facts-computed manifest: pre_task scope cannot load role defaults (the manifest comment documents why), and group_vars is already the declared surface.
- split-hop egress adopts the standalone validated-policy pattern (same family as cascade/split-hop-ingress) instead of extending hook syntax: restores validate-before-load discipline.
- Collision asserts retire only after the checker demonstrably covers each pair (proof recorded in the commit), keeping defense-in-depth documentation.
- Cascade scaffold safety prefers Table = off + documented intent over narrowing AllowedIPs: preserves the topology's activation design space. Convergence refuses before writes when an active or residual historical ingress service, interface, routing entry, or nftables table is present; cleanup is a separately authorized recovery action.

## Contracts and ownership

- New internal role owned here: `ansible/roles/runtime-release` with a `runtime_release_*` surface and contract tests.
- Release consumer migrations are limited to the six roles named by
  `REQ-INSTALL-RELEASE-SHARED` and the two migration steps. Other roles in the
  proposal Impact list participate only in their corresponding concerns;
  watchdog/xray share the P0 template ownership boundary.
- Excluded by cross-change ownership: backup/geodata units (SEC change), TESTING.md idempotence rows (TST change).

## Risks / Trade-offs

- Migrations touch production transport install paths → staged commits, molecule before/after each, snapshot parity where output must be byte-stable.
- Manifest single-sourcing shifts defaults precedence → explicit pytest pinning manifest output against all.yml declarations.
- Liveness waits lengthen converge on genuinely broken hosts → bounded retries matching the xray pattern; failure names the service.

## Migration Plan

- Forward: land shared pieces, migrate consumers one per commit, retire duplicates last after coverage proofs.
- Rollback: revert consumer migration commits independently; shared path is inert when unused.
- Gates: staged molecule runs, full `make ci-fast`, `make validate`, live re-converge with config-snapshot parity.
