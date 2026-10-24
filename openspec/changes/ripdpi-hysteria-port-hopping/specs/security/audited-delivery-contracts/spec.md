## Purpose

Preserve the complete admitted Hysteria hopping policy from producer to the qualified native client.

## MODIFIED Requirements

### Requirement: REQ-AUDIT-HY-COMPATIBILITY — Qualified recipient admission

RIPDPI export MUST retain a valid Hysteria port range and fixed interval in both standard fields and RIPDPI extras. Release admission MUST require the paired native client to pass real-server session continuity across at least three scheduled destination-port changes, including Salamander and IPv6 coverage. A refusal-only implementation MUST NOT qualify. Invalid intervals MUST fail before publication. Other transport compatibility checks MUST remain effective.

#### Scenario: Qualified recipient exports a hopping profile

- **WHEN** the selected RIPDPI profile enables a valid hopping range and interval
- **THEN** standard fields and extras contain the same hopping policy without scalar fallback

#### Scenario: Qualified recipient admission failure boundary

- **WHEN** an interval is below 5000 milliseconds, above 9223372036854 milliseconds, or not an exact whole number of milliseconds
- **THEN** export fails without a payload or credential disclosure

#### Scenario: Client qualification fails

- **WHEN** the paired client cannot keep authenticated traffic across scheduled destination-port changes
- **THEN** release admission remains incomplete and the producer change is not merged
