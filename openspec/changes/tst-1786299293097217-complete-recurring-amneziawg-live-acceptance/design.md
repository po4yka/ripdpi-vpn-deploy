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
- Keep standalone engine provenance separate from client acceptance. A client
  acceptance binds exact RIPDPI source, APK, report and correlation digests,
  timestamps, transport, and all required outcomes.
- Authenticate every client acceptance with a provisioned Ed25519 public key
  and a fresh atomic request. The signature covers the invocation ID, nonce and
  full acceptance; the handoff is consumed once. The deploy repository does not
  implement or impersonate the client signer/relay.
- Bind evidence to exact client/deploy revisions and expiry; both repositories
  validate the same public v4 contract.
- Replace a prior latest PASS only with a later, distinct, validated PASS;
  unavailable infrastructure preserves the prior observation.

## Contracts and ownership

- Deploy owns provisioning, execution, cleanup, recurring scheduling, and the
  canonical manifest schema.
- One executable state machine holds the shared host-lane flock, validates the
  current manifest, records only a valid initial pending observation, and
  publishes latest only after validating a distinct ordered pair. Atomic
  fsynced pending/latest recovery is part of the executable contract; the JSON
  Schema remains structural only.
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
