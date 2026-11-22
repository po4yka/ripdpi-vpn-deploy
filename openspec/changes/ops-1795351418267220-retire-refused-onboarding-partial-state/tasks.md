# OPS-1795351418267220: Retire a refused-onboarding partial staging state through unbound retirement

## Objective

A refused-onboarding prefix (authority, liveness config, executor manifest copy) retires through `make retire-unbound-staging-client` and `make retire-unbound-staging-executor`; every other partial onboarding state still refuses.

## Ownership

`scripts/retire-unbound-staging-client.py`, `tests/unit/test_retire_unbound_staging_client.py`, `docs/reference/protocol-liveness.md`, `.agents/skills/vpn-cleanup/SKILL.md`, `scripts/DESIGN-NOTES.md`, `tests/DESIGN-NOTES.md`. One writer lane.

## Execution

- [x] OPS-1795351768504438 Accept the exact refused-onboarding prefix in unbound retirement and bind its digests #bug @item:OPS-1795351418267220
- [x] OPS-1795351826854045 Add refused-onboarding regression tests and update the runbook, cleanup skill and design notes #bug @item:OPS-1795351418267220

## Verification

- Local: `python3 -m pytest tests/unit/test_retire_unbound_staging_client.py` and `make check`.
- Remote CI: the PR checks on the exact commit.
- Dry-run, staging, live, client and artifact: not applicable; the verbs are local recovery commands that never contact providers or hosts.
