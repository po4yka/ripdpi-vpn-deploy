## ADDED Requirements

### Requirement: REQ-AUDIT-KNOWN-GOOD — Known-good tag from per-node verification

The implementation MUST record a verification receipt for each selected `vpn` host only after `make verify` and its `source-drift` pass, and `make tag-known-good` MUST tag HEAD only when every `vpn` host of every inventory in `KNOWN_GOOD_INVENTORIES` has a receipt for the checked-out revision and deployable digest younger than `KNOWN_GOOD_MAX_AGE_HOURS`. The drift report MUST list only commits since that tag that change deployable paths.

#### Scenario: One node lacks a receipt

- **WHEN** one `vpn` host of a listed inventory has no receipt, a stale receipt, or a receipt for another revision or digest
- **THEN** no tag is created and the refusal names that host.

#### Scenario: A split-hop pair is included

- **WHEN** the operator adds the pair's rendered inventory to `KNOWN_GOOD_INVENTORIES`
- **THEN** the pair's `vpn` hosts are required before the tag is created.

#### Scenario: Documentation commits after the tag

- **WHEN** only documentation or task-record commits follow the latest tag
- **THEN** the drift report lists no intentional drift.
