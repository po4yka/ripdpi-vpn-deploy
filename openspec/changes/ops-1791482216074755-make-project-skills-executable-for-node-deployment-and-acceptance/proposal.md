# Change: Make project skills executable for node deployment and acceptance

Task ID: `OPS-1791482216074755`

## Why

The skill catalog describes task administration more completely than the actual node lifecycle. Operators rediscover bootstrap, exact-node deployment, acceptance and cleanup prerequisites. Long exploration/spec-sync entrypoints obscure their decisions, and workflow handoffs unnecessarily send already-authorized implementation back to the user. Disposable onboarding also requires hand-assembling a private promotion-intent JSON document.

## What Changes

- Add five concise skills: vpn-bootstrap, vpn-deploy, vpn-acceptance, vpn-cleanup and ansible-role.
- Disclose OpenSpec examples conditionally; preserve validated planning and taskctl ownership while continuing already-authorized work across workflow handoffs.
- Add realistic skill evaluation scenarios covering scope, failure, interruption and acceptance boundaries.
- Add a local, credential-free Make verb that assembles and validates one disposable promotion intent and its exact-alias deployment mapping from explicit private inputs.
- Preserve existing runtime gates and publish no synthetic deployment epoch or acceptance receipt. No breaking contract changes.

## Capabilities

### New Capabilities

- `operator-skill-workflows`: task-scoped skill routing, lifecycle guidance and forward-evaluation cases.
- `disposable-intent-preparation`: private no-clobber local intent assembly using the existing validator.

### Modified Capabilities

- None; deployment and promotion enforcement retain their current interfaces.

## Impact

- Project skills and generated tasking asset hashes, operator documentation, Makefile, one local Python preparer and unit tests.
- No provider, Ansible runtime, credential or deployed-node changes; no new dependencies.
