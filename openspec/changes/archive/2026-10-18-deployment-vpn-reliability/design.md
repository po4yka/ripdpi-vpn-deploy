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

## Retained VPN consumer boundaries

Initial site convergence reads accepted AWG claims from the exact private instance record and configurations. It retains the initial firewall in its own shared-publisher transaction. The existing ingress commit records `finish_firewall` with `finish_egress` and completes the fixed firewall helper under the same durable decision. Tagged runs that omit protected consumers must refuse changed public listener authority.

After protected commit, AWG stages its desired firewall and publishes complete executable, unit, configuration and membership candidates through a separate shared transaction. Source builds acquire immutable commit-selected files first. The AWG adapter retains a durable firewall decision for changed and unchanged runtime acceptance. Failed candidate quiescence must be proved before file compensation. Retirement cleanup has its own bounded exact journal so repeated 32-instance changes preserve the supported surface.

The AWG unit must consume its exact admitted configuration directory. The directory is absolute and canonical and excludes whitespace, quotes, percent escapes, control characters and traversal. Read-only unit start admission uses the existing publisher lock boundary to prevent unattended adoption of an interrupted candidate. Legacy upgrade adoption requires exact build-receipt digest authority; retirement does not infer or replace unknown executable authority.

Site baseline defers AWG forwarding removal while protected consumers stage. It admits only the existing exact priority-91 IPv4/IPv6 forwarding fragment through a bounded, root-owned, non-writable, no-follow reader. After a selected AWG consumer completes, the site reuses the existing baseline forwarding entry point with defer disabled. Omitted AWG tags retain prior forwarding. Standalone baseline stays desired-authoritative; forwarding has no new kernel transaction.

## CI image validation dependency

The owner authorized a refresh of the existing Debian13 CI image after its
current immutable digest failed the unchanged HIGH/CRITICAL scan. The existing
publisher uses the same pinned parent and a fresh package upgrade. Accept its
new digest only after the current security gate passes, then update all exact
Molecule consumers and their pin guard together. No production image, provider
or runtime node is changed.
