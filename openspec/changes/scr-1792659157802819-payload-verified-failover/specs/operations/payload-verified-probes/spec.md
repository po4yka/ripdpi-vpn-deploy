## Purpose

Observe useful payload transfer without accepting short successful HTTP responses as evidence.

## ADDED Requirements

### Requirement: REQ-PAYLOAD-EXACT — Verify bounded transferred content

The probe MUST require HTTP 200, exact requested body length and canonical
deterministic content before declaring a transfer complete. It MUST bound sizes,
timeouts and downloads and refuse malformed inputs before network access.

#### Scenario: Short or corrupted successful response

- **WHEN** the endpoint returns HTTP 200 with missing, short, oversized or incorrect content
- **THEN** the probe reports an endpoint/content error and never a completed transfer

#### Scenario: Actual positive transfer

- **WHEN** the endpoint returns the exact requested canonical bytes within the deadline
- **THEN** the probe records completed transfer and measured elapsed time

### Requirement: REQ-PAYLOAD-PATH — Keep transport choice explicit

The probe MUST support direct and explicit loopback SOCKS transport, ignore
ambient proxy configuration and curl configuration, verify HTTPS, and refuse
redirects. A failed SOCKS route MUST NOT retry directly. A bounded standalone
canary MUST provide the canonical content for operator-owned endpoints.

#### Scenario: Proxy environment tries to bypass the selected route

- **WHEN** NO_PROXY or ALL_PROXY conflicts with the explicit transport
- **THEN** actual traffic still uses the explicit route and cannot escape to direct

#### Scenario: Incomplete observations

- **WHEN** only small samples exist or a response cannot be authenticated as the expected payload
- **THEN** the result cannot be healthy and does not assert a censorship cause
