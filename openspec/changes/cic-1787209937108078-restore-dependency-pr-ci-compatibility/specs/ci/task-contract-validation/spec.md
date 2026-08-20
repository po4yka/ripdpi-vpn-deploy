## Purpose

Keep pull-request task-contract validation authoritative for this repository
after the formerly federated peer removes its incompatible task configuration.

## MODIFIED Requirements

### Requirement: REQ-CIC-1787209937108078-001 — validate local contract history

The task-contract job MUST validate this repository's current task contract
and the applicable pull-request or push base history using the pinned local
task tooling. It MUST NOT check out or validate a peer repository that no
longer publishes a compatible federation contract.

#### Scenario: Pull request after peer-contract retirement

- **WHEN** a pull request changes this repository and the former peer lacks
  `tools/tasking/project.json`
- **THEN** local task validation runs against the pull request base and does
  not fail because of that absent peer file

#### Scenario: Invalid local task contract

- **WHEN** this repository's task files violate the local contract
- **THEN** the task-contract job fails
