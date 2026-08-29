---
task_id: ANS-1787497148207353
change: ans-1787497148207353-runtime-pattern-consolidation
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: no separate staging environment exists; per-role molecule gates run before and after each consumer migration
live: required
live_evidence: null
client: not_applicable
client_evidence: no client emitter changed; emitted configs verified byte-stable via molecule snapshots
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-INSTALL-RELEASE-SHARED | ANS-1787496118906923 | runtime-release role contract tests, including refusal and upgrade/rollback semantics | pending |
| REQ-INSTALL-RELEASE-SHARED | ANS-1787496118907057 | xray-runtime, hysteria, hysteria-realm and snell post-migration Molecule results | pending |
| REQ-INSTALL-RELEASE-SHARED | ANS-1787496118906866 | probe-matrix-target and dns-morph-bridge post-migration Molecule results | pending |
| REQ-BUILD-RECEIPT-IDIOM | ANS-1787496118907179 | amneziawg rebuild-decision case with bumped descriptor | pending |
| REQ-UNIT-FLOOR-PARITY | ANS-1787496118907152 | floor-directive contract test across the named Ansible-owned unit templates | pending |
| REQ-LIFECYCLE-GATE | ANS-1787496118907351 | negative-render molecule cases failing at validation for all four formats | pending |
| REQ-SINGLE-SOURCED-DEFAULTS | ANS-1787496118907135 | literal-duplication grep test over roles + manifest; port-change drill | pending |
| REQ-NFT-POLICY-IDIOM | ANS-1787496118907278 | split-hop policy file nft -c validation in molecule | pending |
| REQ-CHECKER-OWNED-COLLISIONS | ANS-1787496118906586 | checker rejection output for the retired assert pairs | pending |
| REQ-P0-SHAPE-SINGLE-SOURCE | ANS-1787496118907125 | shared-template render diff across xray + watchdog fixtures | pending |
| REQ-ACTIVATION-SAFE-SCAFFOLD | ANS-1787496118907037 | scaffold activation rehearsal on scratch namespace showing direct path preserved | pending |
| REQ-MIRROR-RESTORE-ASSERTED | ANS-1787496118907217 | restic-backend molecule case with nested-snapshot fixture failing loudly | pending |

## Gates

- Local: staged per-consumer molecule runs, `make ci-fast`, `make validate`.
- Remote CI: green run on the merge SHA.
- Dry-run: full-inventory `make dry-run` post-consolidation.
- Live: one node re-converged end to end with rendered-config snapshot parity where behavior is intended unchanged.
- Artifact: consolidated runtime path pinned by its own contract tests in CI artifacts.
