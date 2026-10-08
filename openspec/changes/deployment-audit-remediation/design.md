## Context

The proposal records the security and lifecycle regressions. The integration base
already repairs observability ingress reload; preserve that positive capability
and verify it instead of reintroducing the earlier shared-nginx implementation.

## Goals / Non-Goals

- Goal: repair all 21 audit items or demonstrate their existing correction with regression evidence.
- Non-goal: mutate providers, production secrets, remote nodes or fleet acceptance state.

## Decisions

- Preserve controller ownership, exact-node targeting and existing SSH/promotion proof requirements. Update every caller instead of adding bypass flags.
- Terraform owns provider attachment; Ansible owns persistent guest address configuration. Validate all namespaces against the saved-plan snapshot used for apply.
- Keep Hysteria unprivileged; nftables owns port redirection. Baseline owns the effective forwarding decision and safe resolver transition.
- Service lifecycle uses explicit binary/config/credential change results and existing rollback boundaries. Candidate Xray configurations validate with the same asset directory as the service before publication.
- Fresh-node CI must acquire SSH identity through an authenticated trust channel, complete canonical Tailnet bootstrap and SSH recovery/ownership, and retain explicit CI input setup. Trust-on-first-use and secrets in Terraform/cloud-init are prohibited. Source regression evidence is separate from live CI acceptance.
- Drift compares canonical rendered configuration with normalized remote data; unavailable data fails and secret values never enter diagnostics.
- Regressions exercise actual task execution, renderers, policy evaluation and isolated orchestration. Mocks establish local orchestration only, never live acceptance.

## Contracts and ownership

- Runtime worker: Ansible except honeypot, matching isolated tests and role notes.
- Infrastructure worker: Terraform policies, secrets validator, policy-check scripts, honeypot guest address lifecycle and matching tests/notes.
- Primary: Makefile, saved-plan application, operator scripts, vpnd, CI callers, shared documentation, snapshots and all task/spec lifecycle.
- Shared files are serialized through the primary; workers do not commit or edit task state.

## Risks / Trade-offs

- Controller adoption requires explicit existing proof inputs; regression tests must cover successful invocation as well as early rejection.
- DNS/forwarding and hopping affect connectivity; render and local execution evidence precede hosted Molecule checks. Live rollout remains outside this PR.
- Runtime activation and rollback may interrupt service on deployment; preserve old ready state on failure.
- Exact saved-plan enforcement adds a policy prerequisite; dependencies stay repository-pinned and no new production library is introduced.

## Migration Plan

Apply the source PR after local and hosted validation and independent review.
Operators use the existing controller proof inputs through every entry point.
Infrastructure rollout requires separate authorization and runtime acceptance.
Revert source commits before deployment if needed; deployed runtime rollback must
use validated configuration and existing recovery mechanisms. Do not close this
task while required source/CI evidence is outstanding.
