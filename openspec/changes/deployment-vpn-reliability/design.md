## Context

The six audited defects cross orchestration, state selection and runtime consumer
acceptance. The source fix must preserve current safety gates and layer ownership.

## Goals / Non-Goals

- Goal: close the six failure paths with executable regression evidence.
- Non-goal: deploy, rotate credentials, change protocol pins, or accept production.

## Decisions

- Call dependent Make goals separately and sanitize inherited Make controls.
- Validate dry-run intent before private input acquisition.
- Keep the existing encrypted backup layout; match the complete timestamp suffix.
- Initial firewall publication has a retained transaction through protected commit
  and retains accepted AWG policy. The AWG consumer publishes
  desired policy after protected transports commit, under its own retained transaction.
  Protected staging restores its preceding complete policy on refusal. AWG rollback
  restores the post-protected policy, so it cannot undo committed protected ports.
  Credential rotation uses the same staged consumer firewall path. Tagged runs
  preserve omitted accepted consumers or refuse before changing unrelated authority.
- Use the existing retained runtime transaction with a separate AWG state root for
  binaries, shared units, configs, ownership and AWG firewall publication. Stage
  builds at immutable source-selected paths. AWG-specific executable and node bounds
  preserve the supported 32-instance surface; other callers retain their original
  admission limits. Restore complete authority before restarting old instances.
- Reuse the retained-session subprocess supervisor for CI cleanup. Extend private
  stderr capture narrowly if required; do not signal a reaped process identity.

## Contracts and ownership

- Orchestration worker: blue-green, ci-real-deploy, narrow bootstrap_readiness API and focused tests.
- State worker: backup-tf-state, incident recovery recipe and exact-selection tests.
- VPN worker: site and required playbook tasks, firewall, amneziawg, required runtime-release seam and focused tests.
- Primary: task/spec artifacts, shared scripts/tests/ansible notes, integration, reviews, commits and PR.
- No Terraform root, secrets schema or vpnd public interface change is planned.

## Risks / Trade-offs

- Partial compensation can hide outage: test restored bytes and activation, and use
  actual isolated AWG traffic in the hosted native lane where available.
- Runtime recovery authority must remain private and fail closed on foreign state.
- Linux native evidence remains separate from portable orchestration tests.

## Migration Plan

Existing backup names remain valid. Preserve current accepted runtime authority
until candidate acceptance. Rollback uses retained owned files and state; never
remove foreign state. Run focused regressions, make check, applicable Molecule and
native hosted CI, security review and structured review before merge. No external
host mutation is authorized by this source-only PR.
