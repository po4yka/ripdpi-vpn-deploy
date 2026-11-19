# operations/deployment-maintenance-silence Specification

## Purpose
Planned transport restarts during a deploy or a credential rotation must not raise the critical external coverage alert for the node under change, while real coverage loss outside that window and other alerts for the node still notify the operator.

## Requirements

### Requirement: REQ-OPS-DEPLOY-SILENCE-SCOPE — Exact coverage silence before node mutation

When maintenance silence is configured, the deploy controller in deploy mode and the device-lifecycle `rotate-credentials` step MUST create one finite silence on the configured collector's silence gateway before the first mutating playbook for a node starts. The silence MUST match exactly the configured gateway environment, the node's `observability_node_id` and `component=observability-external-coverage`, and nothing broader. Dry-run, check and verify-only runs MUST NOT create a silence.

#### Scenario: Deploy silences only the coverage alert of the target node

- **WHEN** an operator runs `make deploy` for one node with maintenance silence configured
- **THEN** the gateway receives one create request whose matchers are the environment, that node's observability node id and the external coverage component, before `site.yml` starts

#### Scenario: Dry-run creates no silence

- **WHEN** an operator runs `make dry-run` with maintenance silence configured
- **THEN** no silence request reaches the gateway

#### Scenario: Node without an observability identity is not silenced

- **WHEN** the selected inventory host has no `observability_node_id`
- **THEN** no silence request is sent and the deploy runs unchanged

### Requirement: REQ-OPS-DEPLOY-SILENCE-LIFECYCLE — Finite silence with outcome-dependent end

The main silence MUST have a finite end that does not exceed the gateway's maximum TTL. After the mutation succeeds, the controller MUST create a tail silence with the same matchers that ends five minutes later, and then delete the main silence. After the mutation fails or is interrupted, the controller MUST delete the main silence without a tail silence.

#### Scenario: Success keeps a short tail

- **WHEN** the node mutation exits 0
- **THEN** a five-minute tail silence is created first and the main silence is deleted after it

#### Scenario: Failure restores alerting at once

- **WHEN** the node mutation exits non-zero or the controller is interrupted
- **THEN** the main silence is deleted and no tail silence is created

#### Scenario: Controller death leaves only a finite silence

- **WHEN** the controller process is killed before cleanup
- **THEN** the silence remains only until its finite end, which Alertmanager enforces

### Requirement: REQ-OPS-DEPLOY-SILENCE-FAILURE — Silence failure never blocks the deploy

A configuration, transport, gateway or response failure of any silence operation MUST print one categorical warning on stderr and MUST NOT change the deploy's exit status or skip a mutation. Warnings and errors MUST NOT contain tokens, request bodies or remote diagnostics.

#### Scenario: Unreachable collector

- **WHEN** the collector host is unreachable while the controller creates the silence
- **THEN** stderr shows a categorical warning and the deploy proceeds and exits with the playbook's status

#### Scenario: Incomplete configuration

- **WHEN** only some of the maintenance silence settings are set
- **THEN** stderr shows a categorical configuration warning and the deploy proceeds without a silence

### Requirement: REQ-OPS-DEPLOY-SILENCE-AUTHORITY — Existing gateway authority only

The controller MUST use the existing gateway owner token on the collector host and the existing exact-host and capability admission of the observability operator. It MUST NOT read, copy or create gateway tokens locally, and it MUST NOT add a new secret or role. Without configuration the deploy MUST behave exactly as before and print nothing about silences.

#### Scenario: Unconfigured deploy is unchanged

- **WHEN** none of the maintenance silence settings is set
- **THEN** no collector connection is made and the deploy output has no silence line

#### Scenario: Wrong collector host is refused

- **WHEN** the configured collector host lacks the collector capability or belongs to another environment
- **THEN** no silence is created and a categorical warning is printed
