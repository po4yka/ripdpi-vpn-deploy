## Purpose

Keep per-device traffic metadata off the node by default and remove the fleet-wide fingerprints that a public repository and a borrowed TLS identity create.

## MODIFIED Requirements

### Requirement: REQ-TMD-CLIENT-CADENCE — Bounded client latency probing

Every emitted client document, the standard sing-box artifact and the RIPDPI bundle alike, MUST use a 30-minute `urltest` interval on its `auto` outbound, and the bundle contract examples under `contract/` MUST carry that interval so the client's vendored copies stay byte-identical.

#### Scenario: Standard artifact

- **WHEN** a sing-box document is emitted with at least one proxy outbound
- **THEN** its `auto` outbound has `interval` equal to `30m`.

#### Scenario: RIPDPI bundle

- **WHEN** a RIPDPI bundle is emitted with at least one proxy outbound
- **THEN** its `auto` outbound has `interval` equal to `30m` and the document equals the contract example for that materialization.

#### Scenario: Client drift

- **WHEN** the client's vendored copy of either contract example differs from this repository's file
- **THEN** `contract-sync` fails with a drift error naming the file instead of passing.
