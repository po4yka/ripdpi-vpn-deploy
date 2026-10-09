## Purpose

Provide discoverable project skills that guide the actual node lifecycle and role implementation without adding execution authority or duplicating runtime enforcement.

## ADDED Requirements

### Requirement: REQ-SKILL-LIFECYCLE — Route distinct operator work

The project MUST provide vpn-bootstrap, vpn-deploy, vpn-acceptance, vpn-cleanup and ansible-role skills with discriminating triggers, canonical command references, completion criteria and conditional supporting references.

#### Scenario: Existing-node deployment

- **WHEN** an operator requests an authorized update of named existing nodes
- **THEN** vpn-deploy checks exact inventory scope, uses dry-run before deploy and retains existing authorization within its bounds, without reenrolling the nodes.

#### Scenario: Initial staging bootstrap

- **WHEN** an operator requests one authorized disposable staging node
- **THEN** vpn-bootstrap establishes the guarded cleanup manifest before guest writes and finishes documented recovery, Tailnet and ownership prerequisites before handing off to deployment.

### Requirement: REQ-SKILL-OUTCOMES — Preserve acceptance and cleanup boundaries

The operator skills MUST distinguish source, CI, provider, host, protocol/client and human evidence, and MUST route interrupted cleanup according to its bound or unbound phase without broadening deletion authority.

#### Scenario: Required protocol fails

- **WHEN** a required authenticated protocol check fails or is unverified
- **THEN** acceptance reports that claim as incomplete and completes authorized cleanup without issuing a success claim.

### Requirement: REQ-SKILL-HANDOFF — Continue authorized implementation

OpenSpec skills MUST keep planning-only requests read-only for implementation, and MUST permit an explicitly authorized implementation request to continue through validated planning and apply without a redundant new user turn.

#### Scenario: Missing apply artifact

- **WHEN** implementation is already authorized and required planning artifacts are missing
- **THEN** apply uses proposal to fill and validate the missing artifacts before resuming, asking only for material unresolved scope or authority decisions.

### Requirement: REQ-SKILL-EVALUATION — Exercise decision boundaries

The project MUST retain realistic evaluation requests and expected observable boundaries for skill selection, authorization, failed dry-run, interrupted cleanup and incomplete live evidence.

#### Scenario: Independent evaluation

- **WHEN** the skills are evaluated without the expected answer being provided to the evaluating agent
- **THEN** the observed proposed actions can be compared with the retained criteria without executing live operations or treating the evaluation as live proof.
