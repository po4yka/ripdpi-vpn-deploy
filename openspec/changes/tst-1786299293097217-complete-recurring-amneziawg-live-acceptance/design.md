## Context

The repository already owns disposable provisioning, pinned AWG sources,
fail-closed validators, a recurring local executor, and protocol sentinels.
The missing outcome is one complete observed run tied to the RIPDPI client.

## Goals / Non-Goals

- Goal: make real data flow, lifecycle recovery, and teardown independently verifiable.
- Goal: share a redacted exact-source evidence contract with RIPDPI.
- Non-goal: introduce a new protocol revision or production default.
- Non-goal: store live infrastructure data, secrets, or packet payloads.

## Decisions

- Extend the existing executor and manifest rather than create a parallel lane.
- Model infrastructure absence and product failure as separate terminal states.
- Require one coherent lifecycle run so evidence from unrelated attempts cannot
  be assembled into a false pass.
- Bind evidence to exact client/deploy revisions and expiry; both repositories
  validate the same public contract fixture.

## Contracts and ownership

- Deploy owns provisioning, execution, cleanup, recurring scheduling, and the
  canonical manifest schema.
- RIPDPI owns client construction and acceptance of the client-side result.
- Operator-owned credentials and provider state remain outside Git.

## Risks / Trade-offs

- External capacity may be unavailable; the lane remains blocked rather than green-skipping.
- Live tests cost time and provider resources; run one isolated target and clean up deterministically.
- Evidence can leak network facts; retain categorical results and digests only.

## Migration Plan

Land schema and offline negative-path tests first, then run a manual isolated
acceptance. Enable the existing recurring schedule only after that run passes.
Rollback disables the schedule and leaves the prior provisioning behavior intact.
