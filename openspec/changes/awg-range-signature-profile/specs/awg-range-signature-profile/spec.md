## Purpose

Carry one bounded AWG range and signature profile through server admission and client delivery without changing its wire identity.

## ADDED Requirements

### Requirement: REQ-AWG-RANGE-CONTRACT — Admit a strict wire profile

The producer MUST require `wire_profile=awg-3.1-ranges-v1`, four canonical unsigned decimal header strings or closed ranges, pairwise disjoint intervals, and optional bounded I1-I5 programs with the b, r, rd, rc, and t tags. It MUST reject unknown fields, numeric headers, bare hex signatures, malformed tags, and nonzero S3/S4.

#### Scenario: Valid range profile

- **WHEN** an instance has disjoint ranges and bounded tagged signatures
- **THEN** admission preserves their exact canonical text.

#### Scenario: Unsafe or ambiguous input

- **WHEN** ranges overlap, a signature exceeds the packet bound, or S3 is nonzero
- **THEN** admission fails before rendering or publication.

### Requirement: REQ-AWG-RANGE-DELIVERY — Preserve the complete profile

The implementation MUST preserve all supported wire fields in server render, standalone export, bundle export, and cohort fingerprints. The fingerprint MUST bind the named profile and canonical values. All producers and consumers MUST use the new contract without a legacy fallback.

#### Scenario: Export and import

- **WHEN** an admitted profile is exported and imported by the paired client
- **THEN** both sides compute the same fingerprint and the client uses the same wire parameters.

#### Scenario: Old contract

- **WHEN** an old bundle has numeric headers or no wire profile
- **THEN** the consumer refuses it and requires a fresh export.

### Requirement: REQ-AWG-RANGE-RUNTIME — Require compatible source and real traffic

The implementation MUST admit non-singleton ranges or signatures only for the reviewed AWG 3.1 source pair. It MUST prove bidirectional traffic against the actual source-pinned peer. Candidate qualification MUST NOT promote a production pin or establish physical arm64 acceptance.

#### Scenario: Compatible candidate

- **WHEN** the exact candidate source pair receives an admitted range profile
- **THEN** real peer traffic succeeds with the supported ranges and signature packets.

#### Scenario: Earlier source or rollback

- **WHEN** an earlier source is selected with a range or signature profile
- **THEN** admission refuses it before runtime mutation; rollback requires the matching singleton configuration and client export.
