## Purpose

The provider edge firewall, the collector ingest path, the self-hosted runner lane and the agent settings file each have a gate in the tree, so that a safe state does not depend on a manual step or on the honest side of a boundary.

## ADDED Requirements

### Requirement: REQ-SEC-EIG-EDGE-FIREWALL — Refuse a server that stays without an edge firewall

The plan policy MUST deny a plan in which an UpCloud VPN server already exists and its provider firewall stays off. It MUST allow the plan that creates that server and the plan that turns the firewall on. For every provider it MUST deny a server with no attached provider firewall and a firewall whose inbound default is accept.

#### Scenario: Existing UpCloud server with the firewall off

- **WHEN** a plan leaves an existing UpCloud VPN server with `firewall` false
- **THEN** the policy denies the plan and names promotion as the fix

#### Scenario: First creation

- **WHEN** a plan creates the UpCloud server with `firewall` false
- **THEN** the policy allows the plan

#### Scenario: Server without a firewall on another provider

- **WHEN** a plan has a server resource with no firewall attachment
- **THEN** the policy denies the plan

### Requirement: REQ-SEC-EIG-RELAY-LIMITS — Bound what one node can push to the collector

The collector relay MUST drop every series whose metric name is not in the allowed set and every label that is not in the allowed set. It MUST enforce a limit on the number of series and on label count and label value length for each node certificate. A push over a limit MUST NOT stop ingestion for other nodes, and the collector MUST count the rejected series.

#### Scenario: Unknown metric name

- **WHEN** a node pushes a series with a metric name outside the allowed set
- **THEN** the relay drops the series and the collector's Prometheus does not store it

#### Scenario: High-cardinality push

- **WHEN** one node pushes more series than its limit
- **THEN** the relay rejects the excess, the drop counter increases, and series from other nodes are stored

### Requirement: REQ-SEC-EIG-RUNNER-LANE — Record and check the self-hosted runner controls

`.github/repository-policy.json` MUST record that pull requests from forks need approval for all outside contributors, and `scripts/configure-repository.py` MUST fail its check when the live setting differs. A repository test MUST fail when a workflow other than the named real-VPS lane uses a self-hosted runner label. The image publish workflows MUST run on push only for `main`.

#### Scenario: Second workflow with the label

- **WHEN** a second workflow file names the self-hosted label
- **THEN** the repository test fails and names the file

#### Scenario: Approval setting differs

- **WHEN** the live fork approval setting is weaker than the recorded one
- **THEN** the configuration check exits non-zero

#### Scenario: Push to another branch

- **WHEN** a commit that changes an image is pushed to a branch other than `main`
- **THEN** no publish workflow runs

### Requirement: REQ-SEC-EIG-AGENT-SETTINGS — Keep hooks and shell allow entries out of the agent settings

A repository test MUST fail when the tracked agent settings file has a `hooks` key or a permission allow entry for a shell command.

#### Scenario: Hook added

- **WHEN** the settings file gains a `hooks` key
- **THEN** the test fails

#### Scenario: Current file

- **WHEN** the settings file has only attribution and file permission rules
- **THEN** the test passes
