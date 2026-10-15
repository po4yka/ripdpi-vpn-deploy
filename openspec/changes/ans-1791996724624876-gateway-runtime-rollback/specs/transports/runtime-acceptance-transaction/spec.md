## Purpose

Operator runtime rollback moves every process that executes the pinned Xray release, so the frontend and the private gateways never run different releases after a reported success.

## ADDED Requirements

### Requirement: REQ-PROTO-RTA-GATEWAY-ROLLBACK — Roll back every process that executes the pinned release

Operator runtime rollback MUST retarget the frontend and every owned private gateway unit to the verified previous release in one transaction, MUST prove each main process executes that release before reporting success, and MUST restore the complete previous generation when any unit refuses. Every unit file that binds the release path MUST have exactly one publisher.

#### Scenario: Rollback moves frontend and gateways

- **WHEN** an operator rolls back the runtime on a node with both private gateways
- **THEN** `xray.service` and both gateway main processes execute the previous release and a following ordinary deploy with the newer pin succeeds

#### Scenario: Gateway refuses the rollback candidate

- **WHEN** a gateway unit fails readiness on the rollback candidate
- **THEN** all three units return to the previously accepted release and the rollback reports a categorical refusal
