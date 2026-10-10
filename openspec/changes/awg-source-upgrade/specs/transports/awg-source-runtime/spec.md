## Purpose

Provide observable, testable guarantees for upgrade pinned amneziawg sources with unchanged reviewed wire settings across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-AWG-VERSION — Bind reviewed candidate sources and build inputs

The selected Go and tools runtime pair MUST bind refreshed candidate tags to exact immutable commits, reviewed publication/channel API status, provenance, supported build toolchains and reachable critical/high advisory findings. Every generator and receipt consumer MUST agree. Production promotion MUST require stable eligibility and a completed separately authorized 48-hour staging soak.

#### Scenario: Exact candidate pair builds with recorded inputs

- **WHEN** reviewed candidate sources and toolchain are selected
- **THEN** real binaries build from those commits, receipts bind installed outputs to them, and every repository generator resolves the same pair

#### Scenario: Moved tag, unsupported toolchain or unknown eligibility

- **WHEN** a tag resolves elsewhere, build inputs drift or stable publication/advisory status cannot be established
- **THEN** the upgrade refuses or remains an unpromoted candidate without replacing the current ready runtime

### Requirement: REQ-PROTO-AWG-WIRE — Preserve reviewed packet semantics and zero transport junk

The upgrade MUST retain existing reviewed wire settings and coherent cohort fingerprints across server and supported clients. S3 and S4 MUST remain zero and their current safe-floor policy MUST remain unchanged. RandomTrailers, DisableCookies and new packet modes MUST NOT become enabled by this change.

#### Scenario: Existing technical profiles interoperate

- **WHEN** each supported baseline and cohort is run against the exact candidate server and client cores
- **THEN** handshake and bidirectional sustained TCP UDP DNS succeed and packet/header captures match the declared semantic contract

#### Scenario: Nonzero junk or incompatible semantic change

- **WHEN** a candidate or client requires nonzero S3/S4, an excluded feature or a different unreviewed wire shape
- **THEN** the guard or compatibility gate refuses and the candidate cannot be promoted as unchanged settings

### Requirement: REQ-PROTO-AWG-ADOPT — Prove warm running-process adoption and rollback

The implementation MUST Pin-only and unit-only candidate changes MUST restart all required owned active instances and prove the running executable and sandbox adopt the selected version. Failed build, activation or authenticated readiness MUST preserve or restore the prior complete runtime/configuration and unrelated tunnels. Unchanged repeat MUST be idempotent.

#### Scenario: Two active instances receive pin-only and unit-only changes

- **WHEN** private configuration remains unchanged while a source pin or rendered unit changes
- **THEN** both actual daemons adopt the selected binary or sandbox and an unchanged third convergence does not restart

#### Scenario: Build or readiness failure with foreign tunnel

- **WHEN** a candidate build or active data-plane readiness fails while an unrelated tunnel is active
- **THEN** prior ready owned state remains or is restored, the foreign tunnel is untouched and publication cannot report completed adoption

### Requirement: REQ-PROTO-AWG-ARM64 — Require physical candidate acceptance before promotion

The implementation MUST Candidate acceptance MUST include physical Android arm64 evidence identifying app version, embedded core version and commit, ABI and OS version, at least three reconnect cycles, DNS and bidirectional sustained traffic with S3/S4 zero. Missing physical evidence MUST leave runtime promotion incomplete; issue closure or release notes MUST never replace this proof.

#### Scenario: Physical candidate and control reconnect

- **WHEN** the exact candidate and current control use the same server and bounded path with zero S3/S4
- **THEN** physical reconnects DNS sustained transfer and packet offsets are recorded with exact identities and current floor remains zero

#### Scenario: Hardware unavailable or post-handshake data failure

- **WHEN** the physical runtime is unavailable or handshake succeeds but transport data fails
- **THEN** acceptance records the actual blocker or failure and neither production promotion nor safe-floor relaxation occurs
