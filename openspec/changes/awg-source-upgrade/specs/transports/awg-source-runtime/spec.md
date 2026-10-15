## Purpose

Provide an executable local AmneziaWG source-upgrade candidate without external
infrastructure or claims about physical clients or production deployment.

## ADDED Requirements

### Requirement: REQ-PROTO-AWG-VERSION — Build exact source pairs locally

The implementation MUST bind candidate and control tags to immutable commits,
verify a checksum-pinned compiler, build real Go and tools binaries with bounded
jobs and readonly modules, and reject moved tags. Candidate provenance MUST
state unknown release eligibility explicitly. Deployment defaults MUST remain
unchanged until separately eligible for promotion.

#### Scenario: Exact pairs build

- **WHEN** the local source-candidate target executes
- **THEN** both real pairs build with the recorded toolchain and exact commits

#### Scenario: Ref or toolchain drift

- **WHEN** a tag resolves elsewhere or a toolchain checksum differs
- **THEN** the build fails before runtime acceptance

### Requirement: REQ-PROTO-AWG-WIRE — Exercise retained wire semantics

The local lab MUST exercise each supported candidate/control pairing and both
reviewed scalar-header wire shapes with authenticated bidirectional sustained
TCP, UDP, DNS and at least three reconnects. Captures MUST verify actual handshake
and transport header bytes and offsets. S3/S4 and their safe-floor policy MUST
remain zero/unmodified; excluded modes MUST stay disabled.

#### Scenario: Mixed-version and candidate tunnels

- **WHEN** baseline/candidate, candidate/baseline and candidate/candidate run
- **THEN** both shapes carry real traffic and retain declared header semantics

### Requirement: REQ-PROTO-AWG-ADOPT — Exercise complete local adoption

The lab MUST publish complete source pairs through the existing source publisher,
restart two actual owned daemons for pin-only and unit-only changes, compare
running executable digests and sandbox properties, compensate build and
readiness failures, and preserve a third unrelated tunnel. An unchanged repeat
MUST preserve process identities.

#### Scenario: Warm pair and unit change

- **WHEN** only the pair or unit sandbox changes
- **THEN** both owned daemons adopt the selected executable or sandbox and pass
  authenticated traffic while an unchanged repeat leaves their PIDs intact

#### Scenario: Build or readiness rejection

- **WHEN** a real build command fails or authenticated readiness rejects
- **THEN** prior ready complete source authority and owned traffic remain or
  are restored while the unrelated tunnel's PID and traffic remain intact

### Requirement: REQ-PROTO-AWG-LOCAL — Keep acceptance local and truthful

The target MUST admit only a local Docker daemon, run the runtime lab without
external networking or published ports, copy only explicit public inputs, clean
up its own container on success/failure, and fail on unavailable prerequisites.
Linux arm64 evidence MUST NOT claim physical Android acceptance or relax S3/S4.

#### Scenario: Disconnected local execution

- **WHEN** the target runs on the workstation
- **THEN** real systemd/TUN peers communicate only inside owned namespaces and
  the owned container is removed after the run

#### Scenario: Remote daemon or unavailable prerequisites

- **WHEN** Docker is remote or systemd/TUN is unavailable
- **THEN** the target fails explicitly without a skipped or synthetic success
