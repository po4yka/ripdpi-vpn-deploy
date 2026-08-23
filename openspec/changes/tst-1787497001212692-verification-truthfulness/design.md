## Context

Seven verification-honesty findings share a mechanism: gates assert less than deploy produces, or scenarios test less than their docs claim. The idempotence contract (second converge reports changed=0) is stated in ansible/CLAUDE.md as universal but is enforced nowhere for the integration tests that matter most. Fixing the amneziawg scenario may surface latent task bugs — those are in scope to fix minimally when revealed.

## Goals / Non-Goals

- Goal: verification output is trustworthy for every host class and scenario docs describe reality.
- Non-goal: adding new production runtime behavior; expanding molecule coverage to roles that deliberately have none (documented skips stay).

## Decisions

- Idempotence phases appended to existing sequences rather than a new scenario: the contract applies to the same converge.
- amneziawg converge rewritten around include_role with the existing binary stubs: keeps the scenario hermetic while executing real task code.
- Fallback-listener assertions conditional on fallback_enabled: mirrors deployment conditions, avoids failing hosts that never open those ports.
- TESTING.md synced by observation (read each molecule.yml), not by intent.

## Contracts and ownership

- Playbooks owned here: verify.yml, smoke-test.yml, source-drift.yml.
- Molecule trees owned here: full-stack, full-stack-published, roles/xray, roles/amneziawg.
- docs/TESTING.md edited exclusively within this change.

## Risks / Trade-offs

- Enabling full-stack idempotence can reveal pre-existing non-idempotent tasks → fix minimally and record each fix in the change notes; do not weaken assertions.
- Stricter source-drift can fail legitimately drifted nodes → intended; runbook already prescribes redeploy on drift.
- CI runtime grows with two added idempotence phases → bounded by existing scenario durations.

## Migration Plan

- Forward: single commit per concern; no production state changes.
- Rollback: revert commits independently.
- Gates: touched molecule scenarios, live-inventory verify cycle, `make ci-fast`, `make validate`.
