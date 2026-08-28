## Context

Thirteen deploy-path findings from the audit (2026-08-23) share a theme: the safety rails exist but are skippable, unbounded, or inconsistent across invocation paths. Evidence citations live in the linked portfolio record. All fixes are local to playbooks, scripts, the Makefile dependency graph, one Terraform variable validation block, and group_vars defaults.

## Goals / Non-Goals

- Goal: make the canonical operator path self-enforcing on every invocation shape without changing what gets deployed.
- Non-goal: reworking role internals, listener contracts, or adding new guard systems — existing guards get tags and parity, not replacements.

## Decisions

- Bootstrap gate as a Makefile prerequisite rather than an Ansible pre_task: it keeps the wait outside converge, avoiding dpkg-lock contention by construction.
- Cohort validation against the group_vars file set rather than a second allowlist: single source of truth for profile names.
- SSH allowlist enforced in both Terraform validation and site.yml assert: plan-time failure plus defense in depth for hand-rendered inventories.
- Rotation .prev via copy before template write: reuses the exact contract rollback-config already consumes; no new artifact format.
- Rollback ordering fix is reorder-only plus a no-op guard; no new validation machinery.
- Toggle-default parity for ordinary transport selection is enforced by a pytest sweep of source expressions, including missing-key and explicit boolean behavior. Existing cohorts replace the `vpn` mapping rather than deep-merging it, so omitted keys use inline defaults; explicit cohort values must remain authoritative. The fail-closed `backup-configure.yml` prerequisite is not a transport selector and is excluded without changing its guard.
- Cascade defaults are explicitly false with a governance pointer. Tests require disabled values, not textual absence, while retaining exception-tier, per-host authorization and implementation-only guards.

## Contracts and ownership

- Playbooks owned here: site.yml, smoke-test.yml, os-maintenance.yml, rotate-credentials.yml, rollback-xray.yml.
- Scripts owned here: wait-cloud-init.sh, render-inventory.sh (shellcheck-gated).
- Makefile targets touched: deploy, dry-run, new bootstrap-readiness target.
- terraform/providers/*/variables.tf: additive validation block only; no output schema change.

## Risks / Trade-offs

- Deploy now blocks on bootstrap completion → slower but honest; SKIP-style escape hatch intentionally NOT added (the runbook already sequences manual steps).
- Stricter renderer failures can break ad-hoc HOSTS strings that previously half-worked → intended fail-loud behavior.
- Restart-based AWG/rollback changes briefly interrupt service during maintenance windows → acceptable; documented.

## Migration Plan

- Forward: single commit per concern; no state migration required.
- Rollback: revert playbook/script commits independently.
- Gates: named pytest cases, shellcheck, `make ci-fast`, `make validate`, live-inventory dry-run before merge.
