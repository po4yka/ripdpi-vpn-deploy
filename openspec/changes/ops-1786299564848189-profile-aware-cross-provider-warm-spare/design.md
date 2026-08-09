## Context

The repository has provider-specific Terraform roots, provider-neutral Ansible,
a fleet registry, protocol liveness, and operator-gated warm-spare promotion.
The current active topology assigns each profile to one provider/node.

## Goals / Non-Goals

- Goal: prove one complete cross-provider redundant profile as a vertical slice.
- Goal: reuse current liveness and rotation safety boundaries.
- Non-goal: automate every region/profile or auto-promote production traffic.

## Decisions

- Start with one critical profile; generalize only after staging evidence.
- Use separate provider/environment state and credentials with a shared reviewed source revision.
- Extend the fleet registry with logical-profile active/spare roles rather than encode provider logic in Ansible.
- Consume the recurring filtered-vantage verdict and require explicit final confirmation.

## Contracts and ownership

- Terraform owns independently disposable nodes and isolated state.
- Ansible owns identical profile convergence from the selected source revision.
- Monitoring owns active/spare health; operations owns promotion and rollback.
- Secrets remain operator-owned and separate per node/client.

## Risks / Trade-offs

- Additional infrastructure has cost; limit the first slice to one critical profile.
- Correlated configuration can break both nodes; exact-source parity is required
  but independent provider checks and staging drills remain necessary.
- Incorrect promotion can extend an outage; fail closed on any stale, unknown, or drifted input.

## Migration Plan

Add registry and planning support, provision an isolated staging pair, converge
both nodes, and exercise promotion/rollback. Production enrollment requires a
later explicit operator decision after recurring liveness evidence is available.
