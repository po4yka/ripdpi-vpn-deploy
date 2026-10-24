## Purpose

Keep the reviewed Xray pin check accurate when upstream publishes a newer release that still needs local qualification.

## ADDED Requirements

### Requirement: REQ-XRAY-REVIEWED-PIN — Check the reviewed local pin

The pin checker MUST compare exactly one repository-pin heading with the example pin. It MUST reject a missing, duplicate, or mismatched declaration. Upstream Latest status MUST remain independent and MUST NOT authorize a production change.

#### Scenario: New upstream security release

- **WHEN** the release tracker records a newer Latest release and the existing reviewed repository pin
- **THEN** parity succeeds only against that repository pin and the staging policy remains required.

#### Scenario: Ambiguous pin

- **WHEN** the tracker contains two repository-pin declarations or none
- **THEN** parity fails without accepting the first match.
