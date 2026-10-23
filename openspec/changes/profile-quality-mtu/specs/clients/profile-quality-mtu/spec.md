## Purpose

Deliver bounded, verifiable transfer-quality selection and packet-size diagnosis
through the existing recipient runtime without inventing network evidence.

## ADDED Requirements

### Requirement: REQ-QUALITY-CONTRACT — Admit a complete coordinated quality policy

The producer and recipient MUST implement payload failover policy version 2.
They MUST reject version 1 wire input rather than maintain a second policy implementation.
The optional quality object MUST contain only max_pass_bytes, max_window_bytes,
window_seconds, minimum_gain_percent and maximum_loaded_latency_increase_ms.
Both HTTPS object origins MUST remain distinct, with exact expected lengths
between 32768 and 1048576 bytes and SHA256 digests. All contributing hosts MUST
agree. Quality configuration MUST be absent unless explicitly configured.

#### Scenario: Complete bounded policy

- **WHEN** an operator configures version 2 quality with a pass budget sufficient for both targets on the active and challenger members
- **THEN** the emitted bundle and paired recipient retain every field and enable the same existing selector
- **AND** the version 2 policy without quality retains payload-health failover

#### Scenario: Malformed, obsolete or conflicting policy

- **WHEN** a policy has unknown fields, version 1, invalid numerical bounds, too little pass capacity or conflicting host values
- **THEN** validation refuses before publication or activation without exposing inputs

#### Scenario: Upgrade an existing recipient catalog

- **WHEN** a recipient has a persisted version 1 health-only policy from the previous application version
- **THEN** one checked local storage migration retains its profiles and choices under version 2 health-only policy
- **AND** failed persistence leaves the original data intact and version 1 wire imports remain rejected
- **AND** the migrated catalog accepts a subsequent validated version 2 subscription refresh

### Requirement: REQ-QUALITY-MEASUREMENT — Measure actual verified transfer quality

The recipient MUST measure goodput from exact digest-verified body bytes and a
positive monotonic body duration through the candidate's actual encrypted path.
It MUST measure baseline and loaded HTTPS HEAD transaction latency against the
same admitted object without redirects, retries or direct fallback. A HEAD
response MUST establish the expected status and object length. Loaded latency
MUST be authoritative only when the complete control transaction overlaps an
actual body transfer, from the first positive body read through EOF before final
digest comparison. An incomplete overlap MUST preserve valid goodput as
partial evidence and MUST NOT become a zero latency, a path failure or a claim
of measured load. Request latency MUST NOT be labeled packet RTT or bandwidth.

#### Scenario: Fast handshake with slow useful transfer

- **WHEN** the active member has a fast handshake but a verified slow body and a challenger delivers a faster verified body
- **THEN** the recorded goodput reflects useful transfer instead of handshake order
- **AND** control timings and complete load overlap remain independently observable

#### Scenario: Invalid content, cancellation or fast transfer

- **WHEN** a digest fails, the operation is cancelled, the network changes or the body completes before the loaded control
- **THEN** invalid or stale measurements cannot select a member
- **AND** a completed verified body with insufficient overlap remains partial rather than a fabricated complete result

### Requirement: REQ-QUALITY-BUDGET — Bound work before network activity

The recipient MUST reserve body-read allowance before each attempt under one
serialized pass and durable application window ledger. The allowance MUST
include the extra byte used to detect an oversized body. Failed, cancelled and
partial attempts MUST consume their reservation. Network changes, policy
changes, reimport and process restart MUST NOT replenish the active window.
Clock changes MUST NOT grant an early refill. Headers, attempts, concurrency
and operation time MUST also be bounded. The budget MUST describe application
body allowance, not complete encrypted wire traffic. Exhaustion MUST defer
measurement without recording a transport failure or switching to direct.

#### Scenario: Window exhaustion and restart

- **WHEN** earlier attempts consume the window and the app restarts or imports a changed policy
- **THEN** the next attempt remains deferred until the retained window permits it
- **AND** no socket opens without the necessary reservation

#### Scenario: Several eligible groups

- **WHEN** multiple selector groups request measurements concurrently
- **THEN** one shared ledger prevents over-admission and each round retains its own pass cap

### Requirement: REQ-QUALITY-SELECTION — Improve the existing selector without oscillation

The existing selector MUST compare a healthy active member with a bounded
rotating challenger. It MUST require complete, current measurements and the
existing recovery threshold of consecutive wins before quality promotion.
A goodput win MUST meet minimum_gain_percent without exceeding the allowed
loaded-latency increase. A loaded-latency win MUST meet minimum_gain_percent
with non-regressing goodput. Cooldown, backoff, manual selection, configuration
identity, network scope and native cleanup fences MUST remain authoritative.
Existing transport-health failure recovery MUST continue. Direct, unsupported
members and the separate AmneziaWG tunnel MUST NOT enter the relay selection
pool through this change.

#### Scenario: Stable improvement

- **WHEN** a challenger repeatedly has qualifying goodput or loaded-latency improvement on the current scope
- **THEN** the existing selection lifecycle applies it once after the threshold and cooldown
- **AND** small fluctuations or stale results do not switch the member back

#### Scenario: Manual choice, failed cleanup or no qualified challenger

- **WHEN** the user pins a member, candidate cleanup remains pending or no challenger has complete qualifying evidence
- **THEN** automatic quality promotion does not overwrite that authority
- **AND** the current encrypted selection is retained

### Requirement: REQ-QUALITY-DIAGNOSIS — Explain quality and packet-size evidence

The recipient MUST show current verified goodput, baseline and loaded request
latency, partial or unavailable reasons, selection reason and remaining budget
without exposing credentials or target addresses. MTU diagnosis MUST reuse the
existing non-root packet probe and distinguish configured interface MTU,
acknowledged UDP payload lower bound and family-specific IP packet lower bound.
It MUST preserve direct-path scope and revoke current authority on network
changes. Search losses or an HTTP body-size cliff MUST NOT prove exact PMTU,
tunnel MTU, filtering or a path black hole. It MUST NOT change AWG or server MTU.

#### Scenario: Confirmed packet-size evidence

- **WHEN** a current direct IPv4 or IPv6 QUIC probe validates TLS, prevents fragmentation and acknowledges an increased UDP payload
- **THEN** diagnosis reports the observed lower bound and the corresponding family-specific IP packet lower bound
- **AND** it explains that neither value measures the VPN tunnel or exact PMTU

#### Scenario: Missing or stale packet evidence

- **WHEN** the probe is unsupported, inconclusive, cancelled or belongs to a changed network
- **THEN** diagnosis reports that limitation without a current numeric MTU recommendation

### Requirement: REQ-QUALITY-ACCEPTANCE — Exercise the positive capability

Completion MUST include real socket tests with verified bodies, concurrent
control requests, shaped transfer quality, cancellation and byte-budget bounds.
The paired client MUST execute its production measurement and existing selector
path with owned native runtimes. Packet-size diagnosis MUST retain real QUIC
IPv4 and IPv6 coverage. Contract fixtures, independent review, local gates and
protected exact-source PR and main CI MUST pass. Refusal-only implementations,
mocks or an unexecuted test plan MUST NOT close this feature. Isolated runtime
proof MUST NOT be reported as a fleet deployment or physical-device acceptance.

#### Scenario: Native quality selection

- **WHEN** owned native candidates expose a slower verified body or increased loaded latency
- **THEN** actual measurement and selector execution demonstrate the configured improvement and hysteresis
- **AND** native handles, sockets and owned test resources are released
