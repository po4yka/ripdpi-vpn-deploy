## Purpose

Provide observable, testable guarantees for align xhttp endpoint paths forwarded attribution and served origins across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-XEC-PATH — Canonical endpoint path across consumers

Every accepted XHTTP path MUST follow one strict canonical grammar consumed identically by nginx Xray recipient export and liveness profiles. Unsupported paths MUST refuse before role mutation and MUST NOT be repaired with hidden normalization or duplicate compatibility locations.

#### Scenario: Canonical path forwards

- **WHEN** an accepted path is rendered exported and used by the exact supported XHTTP client
- **THEN** the request reaches the expected backend and authenticated payload transfer completes

#### Scenario: Invalid path fails before mutation

- **WHEN** root trailing slash query whitespace or directive-control path input is selected
- **THEN** schema or semantic validation refuses categorically before changing files services or private artifacts

### Requirement: REQ-PROTO-XEC-ATTRIBUTION — Sanitized source attribution

The direct nginx frontend MUST provide only a sanitized actual peer source to the XHTTP backend through the exact runtime's supported header contract. Client-supplied forwarding headers MUST NOT override or fabricate source identity on either frontend.

#### Scenario: Actual recipient source is observed

- **WHEN** a controlled peer completes an authenticated request through the primary or alternate direct frontend
- **THEN** backend attribution matches the actual peer rather than loopback

#### Scenario: Supplied forwarding authority is rejected

- **WHEN** the peer supplies forwarding headers with a different source identity
- **THEN** the observed backend source remains the actual peer and no supplied identity is trusted

### Requirement: REQ-PROTO-XEC-ORIGIN — Public identity names a served origin

The implementation MUST Primary canonical origin MUST include the effective nondefault HTTPS port and agree across extra-vars nginx preflight discovery metadata redirects and Hysteria masquerade. Unsupported schemes credentials paths fragments and mismatching host or port MUST refuse before activation.

#### Scenario: Default and nondefault HTTPS ports work

- **WHEN** the primary public listener uses port 443 or an approved distinct port
- **THEN** absolute metadata feed sitemap and redirect URLs refer to the actual served primary origin and the owned masquerade target responds

#### Scenario: Origin disagrees with served identity

- **WHEN** a supplied origin disagrees with effective host port or HTTPS grammar
- **THEN** validation refuses without replacing the accepted nginx or Hysteria authority

### Requirement: REQ-PROTO-XEC-PRESERVATION — Keep transactions privacy and exact client support

The implementation MUST Endpoint contract changes MUST preserve integrated nginx validation compensation and transport log privacy. Failed candidate activation MUST restore the prior served authority. Generated artifacts MUST contain only selected device material and MUST use an exact client that supports XHTTP.

#### Scenario: Invalid endpoint candidate preserves service

- **WHEN** a candidate endpoint change fails complete native validation or activation
- **THEN** the prior served configuration remains restartable and authenticated requests recover through it

#### Scenario: Artifacts and logs retain private boundaries

- **WHEN** a selected synthetic device profile is exported and primary or alternate requests succeed or fail
- **THEN** unsupported standard-client artifacts are refused and diagnostics or ordinary logs contain no bearer path or credential value
