## Purpose

Keep per-device traffic metadata off the node by default and remove the fleet-wide fingerprints that a public repository and a borrowed TLS identity create.

## ADDED Requirements

### Requirement: REQ-TMD-BUNDLE-CADENCE — Bundle latency probing matches the standard artifact

The RIPDPI bundle's `auto` outbound MUST use the same 30-minute `urltest` interval as the standard sing-box artifact, and the bundle contract examples under `contract/` MUST carry that interval so the client's vendored copies stay byte-identical.

#### Scenario: RIPDPI bundle

- **WHEN** a RIPDPI bundle is emitted with at least one proxy outbound
- **THEN** its `auto` outbound has `interval` equal to `30m` and the document equals the contract example for that materialization.

#### Scenario: Standard artifact unchanged

- **WHEN** a standard sing-box document is emitted from the same inputs
- **THEN** its `auto` outbound has `interval` equal to `30m`, so no format-specific probe cadence remains.

#### Scenario: Client drift

- **WHEN** the client's vendored copy of either contract example differs from this repository's file
- **THEN** `contract-sync` fails with a drift error naming the file instead of passing.
