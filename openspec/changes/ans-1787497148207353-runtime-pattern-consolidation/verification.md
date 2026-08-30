---
task_id: ANS-1787497148207353
change: ans-1787497148207353-runtime-pattern-consolidation
commit_sha: "841c19268f83f21971683bc78791a002f600fc1f"
local: required
local_evidence: "Exact source 841c19268f83f21971683bc78791a002f600fc1f passed the canonical build-gate make -j1 check: 2487 Python tests plus 1 existing skip, 55 BATS, 184 Rust release tests and Clippy, 87 Terraform mocks, 45 Conftest policies, and ci-fast; log SHA256 745b471b937c85dbb2bb51218ce39ba55e0fde0761af6a494084e3dceb99e2cb. Runtime-release contract module 71 PASS under restrictive umask. Isolated native root-Ansible acceptance on exact runtime source 680a40fb5623d291b4975cb9543f58ec9d4bc9fe produced result SHA256 c28fd725a1dfcd4ae70a3c5062fd6b073dc26fed14e1316412ee05de1c046583 with cleanup, profile stop, Docker context, and config equality confirmed."
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
artifact_evidence: receipt-owned binary and archive release fixtures validated with strict local HTTPS, serialized same-pin publication, failure cleanup and foreign-replacement retention
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-INSTALL-RELEASE-SHARED | ANS-1787496118906923 | 71 contract tests under restrictive umask; isolated native root-Ansible binary/archive install, idempotence, upgrade links, failure-to-retry cleanup, exactly-one same-pin publication, and foreign-replacement retention on source commit `680a40fb5623d291b4975cb9543f58ec9d4bc9fe` with result SHA256 `c28fd725a1dfcd4ae70a3c5062fd6b073dc26fed14e1316412ee05de1c046583`; canonical full gate on exact combined source `841c19268f83f21971683bc78791a002f600fc1f` | local/native pass; hosted integration pending |
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
