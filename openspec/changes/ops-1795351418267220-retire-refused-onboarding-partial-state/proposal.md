# Change: Retire a refused-onboarding partial staging state through unbound retirement

Task ID: `OPS-1795351418267220`

## Why

On 2026-11-22 a disposable staging run refused at onboarding (`onboarding-refused`) after promotion finalization had written its authority epoch, liveness config and executor manifest copy. After `make staging-destroy` verified provider absence, no supported verb could finish cleanup: `make deonboard-disposable-liveness` needs a binding that never existed, and `make retire-unbound-staging-client` refused every onboarding output with `retirement-bound`. The operator had to move the files by hand before the unbound path would run.

## What Changes

- `retire-unbound-staging-client.py` accepts one extra input shape: the prefix that `disposable_promotion.finalize` writes before its installer step (authority, then liveness config, then executor manifest copy), when each file is exactly what the retained intent produces. Binding, registry, pending registry and promotion config stay refused, as do a gap in that order and any other content.
- Present partial outputs are retained in place, and their SHA-256 digests join the journaled request (and so the receipt's request digest). A clean run's request is unchanged.
- `retire-unbound-staging-executor.py` inherits the same check because it reuses the client input validation.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `clients/config-registry`: unbound staging retirement admits the exact refused-onboarding prefix.

## Impact

- Scripts: `scripts/retire-unbound-staging-client.py` (and through it `scripts/retire-unbound-staging-executor.py`).
- Docs: `docs/reference/protocol-liveness.md`, `.agents/skills/vpn-cleanup/SKILL.md`, `scripts/DESIGN-NOTES.md`, `tests/DESIGN-NOTES.md`.
- No Terraform, Ansible, secrets schema or client payload change. No provider or host contact.
