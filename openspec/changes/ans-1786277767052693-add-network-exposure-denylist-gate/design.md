## Context

Portfolio task `ANS-1786277767052693` owns this change. The repository already has a canonical Ansible firewall layer, strict secret handling, check-mode gates, and disposable-node recovery. This feature must add a review boundary without turning source control into an address feed, allowing hidden network mutation, or crossing Terraform/Ansible ownership.

## Goals / Non-Goals

- Goal: validate reviewed metadata and explicit directional policy before rendering any rule input.
- Goal: preserve existing render and host state when disabled.
- Goal: provide redacted dry-run, log-only, canary, expiry, and rollback behavior with regression tests.
- Non-goal: ship address ranges, provider rules, an automatic feed updater, or default-on enforcement.
- Non-goal: activate the feature on a live fleet as part of implementation.

## Decisions

- A dedicated Ansible role owns validation, plan construction, and mode selection; the existing firewall role remains the sole runtime firewall renderer.
- Input is an operator-reviewed artifact outside Git. Repository-owned schema and placeholder fixtures describe shape only. Metadata includes schema version, repository-local source ID, creation/expiry, content digest, review identity, signature metadata, and separate directional intents.
- The role validates before template rendering and passes a typed, normalized plan to the firewall integration. Disabled mode passes no plan and therefore preserves the existing render.
- Modes are `disabled`, `log_only`, `canary`, and `enforce`. Defaults select `disabled`; every other mode requires an explicit reviewed artifact and configuration.
- Refresh is a manual-reviewed artifact replacement. No timer, remote fetch, or implicit apply path is introduced.
- Dry-run summaries expose aggregate counts, source ID, direction, state, and digest only. Address values and host-specific inventory never enter logs.

## Boundaries and ownership

- Terraform remains unchanged and owns no denylist data.
- Ansible owns validation and runtime configuration through the new role plus a narrow firewall input contract.
- SOPS+age continues to own secret material; the feed is non-secret but may still be supplied outside Git because it is deployable policy.
- `vpnd`, if changed, may invoke and present the canonical Make/Ansible dry-run only; it cannot implement policy or fetch data.
- Shared `ansible/group_vars/`, the site playbook, and firewall templates are serialized single-writer paths.

## Risks / Trade-offs

- A false positive can block required traffic. Mitigation: disabled default, separate directions, log-only observation, canary scope, expiry, and documented rollback.
- A stale or substituted feed can create incorrect policy. Mitigation: digest/signature/review/expiry validation before render.
- Redacted output can hide debugging context. Mitigation: preserve counts, source ID, direction, state, and digest while keeping raw content in the operator-controlled artifact.
- A later updater could bypass review. Mitigation: repository checks reject fetch/timer paths in feature-owned files and the normative spec forbids implicit refresh.

## Migration and rollback

Land schemas, placeholder fixtures, validators, disabled defaults, tests, and documentation first. Verify byte-equivalent disabled rendering. Exercise log-only mode only in an isolated staging inventory. Promotion to canary or live enforcement requires a later owner-authorized change with exact-SHA staging evidence. Rollback sets the mode to `disabled`, reapplies the canonical firewall render, and verifies removal of feature-owned rule state.

## Validation strategy

- Schema and negative fixture unit tests.
- Static policy test rejecting deployable address/rule content in repository fixtures.
- Snapshot or semantic comparison proving disabled output equivalence.
- Molecule coverage for invalid input, log-only output redaction, check mode, idempotence, and rollback.
- `make task-check`, full unit tests, remote CI, and an isolated staging dry-run before archive.
