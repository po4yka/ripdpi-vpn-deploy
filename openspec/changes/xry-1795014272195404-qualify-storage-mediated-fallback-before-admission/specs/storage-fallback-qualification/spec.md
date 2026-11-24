## Purpose

Qualify an experimental fallback without exposing account material or confusing synthetic compatibility with real path effectiveness.

## ADDED Requirements

### Requirement: REQ-STO-REVIEW — Versioned admission review

The qualification MUST pin and review source revisions, license obligations, client interoperability and threat boundaries. Unknown results MUST block admission. The report MUST name each client it exercised by implementation, revision and platform. The upstream reference client proves protocol compatibility only; RIPDPI client support stays unclaimed until a peer task in the client repository exercises it.

#### Scenario: Unsupported client

- **WHEN** the chosen client cannot interoperate with the reviewed runtime
- **THEN** the report rejects admission and no bundle field or default changes.

### Requirement: REQ-STO-HARNESS — Harness-only Xray prerequisites

The harness MUST pin one Xray revision (v26.11.9 or a later reviewed release) for both client and server, separate from the production `xray.version` pin, and the review MUST record that release in the Xray release-line reference. The fixture MUST enable VLESS Encryption and Multiplex only in harness configuration, because upstream requires both for XDRIVE and production profiles keep `decryption` set to `none`.

#### Scenario: Harness revision differs from the production pin

- **WHEN** the harness runs an Xray revision or VLESS Encryption setting that production does not use
- **THEN** the production `xray.version` pin and every production profile stay unchanged, and the report lists the pin and encryption changes that a later integration would need.

#### Scenario: Release changes shared Multiplex behavior

- **WHEN** the harness release changes behavior for every Multiplex user, such as the v26.11.9 increase of the mux.cool minimum concurrency to 128
- **THEN** the release-line entry records that change as an input to any later production pin upgrade.

### Requirement: REQ-STO-HOLD — VLESS Encryption stays on HOLD

VLESS Encryption stays under the HOLD phase of ADR 0006 (`docs/decisions/0006-pq-reality-adoption.md`). The harness MUST NOT add a secret, schema field, Ansible variable, environment override, Make target, client field or bundle field for it.

#### Scenario: Admission while VLESS Encryption is on HOLD

- **WHEN** the qualification admits XDRIVE while ADR 0006 is in the HOLD phase
- **THEN** the report marks integration as blocked by ADR 0006, and only a reviewed change that moves ADR 0006 to STAGING can enable VLESS Encryption in any environment.

### Requirement: REQ-STO-FIXTURE — Isolated failure qualification

The harness MUST use the exact pinned candidate client/server against local synthetic fixtures with no real accounts, secrets or external services. It MUST reject substitute candidate mocks as evidence and block qualification if isolation needs material protocol rewriting.

#### Scenario: Lifecycle and resource failures

- **WHEN** a peer disconnects mid-transfer, the storage quota is exhausted, objects are delayed, replayed, reordered or deleted early, or buffers reach their limits
- **THEN** the fixture records bounded failure, byte integrity and cleanup evidence without exposing account material, and the report reviews confidentiality separately from obfuscation.

#### Scenario: Objects remain after the connection ends

- **WHEN** a connection closes normally, is cancelled or times out
- **THEN** the fixture lists the storage backend and records every object the candidate left behind, and the report treats unbounded retention as an admission blocker.

#### Scenario: Fixture requests external access

- **WHEN** a test attempts to use a non-fixture address or account material
- **THEN** execution stops before contact and reports an authorization boundary rather than a passing test.

### Requirement: REQ-STO-DECISION — Explicit evidence and rollback

The report MUST record measured payload delivery, bounded failure behavior, cleanup, confidentiality gaps, latency and resource cost, comparing to the unchanged baseline. It MUST distinguish synthetic results from separately authorized path measurements and permit a reject outcome.

#### Scenario: Control channel works but payload fails

- **WHEN** session setup succeeds but controlled application bytes are not delivered intact within the budget
- **THEN** the result is failure, not successful circumvention, and all fixture resources are cleaned up.
