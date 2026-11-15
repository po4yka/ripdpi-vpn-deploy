## Purpose

The provider edge firewall, the collector ingest path, the self-hosted runner lane and the agent settings file each have a gate in the tree, so that a safe state does not depend on a manual step or on the honest side of a boundary.

## ADDED Requirements

### Requirement: REQ-SEC-EIG-EDGE-FIREWALL — Refuse a server that stays without an edge firewall

The plan policy MUST deny a plan that changes resources while an existing UpCloud server keeps its provider firewall off. It MUST allow first creation or replacement, promotion, the completion of an interrupted first apply, and a plan with no resource change. For every other provider it MUST deny a server with no attached provider firewall and a firewall whose inbound default is accept.

#### Scenario: Existing UpCloud server with the firewall off

- **WHEN** a plan changes a resource and leaves an existing UpCloud server with `firewall` false
- **THEN** the policy denies the plan and names promotion as the fix

#### Scenario: Interrupted first apply or empty plan

- **WHEN** a plan still creates the firewall rules of an existing UpCloud server, or changes no resource
- **THEN** the policy allows the plan

#### Scenario: First creation

- **WHEN** a plan creates the UpCloud server with `firewall` false
- **THEN** the policy allows the plan

#### Scenario: Server without a firewall on another provider

- **WHEN** a plan has a server resource with no firewall attachment
- **THEN** the policy denies the plan

#### Scenario: Attachment known only after apply

- **WHEN** a plan creates a server whose firewall reference is not known until apply
- **THEN** the policy allows the plan

### Requirement: REQ-SEC-EIG-RELAY-LIMITS — Bound what one node can push to the collector

The collector relay MUST drop every metric name and label outside the sender's allowed set, and a repository test MUST fail when the two lists differ. The relay MUST limit label count and length for each series, and unique series for each hour to one budget for each enrolled node, summed for the whole relay. A push over a limit MUST NOT fail, and the relay MUST count the rejected series.

#### Scenario: Unknown metric name

- **WHEN** a node pushes a series with a metric name outside the allowed set
- **THEN** the relay drops the series and the collector's Prometheus does not store it

#### Scenario: High-cardinality push

- **WHEN** one node pushes more unique series than the relay's hourly limit
- **THEN** the relay drops the excess, its drop counter increases, and series that other nodes already send are stored

### Requirement: REQ-SEC-EIG-RUNNER-LANE — Record and check the self-hosted runner controls

`.github/repository-policy.json` MUST record that fork pull requests need approval for all outside contributors. `scripts/configure-repository.py` MUST plan a change when the live setting differs and MUST refuse a weaker recorded value. A repository test MUST fail when a workflow other than the real-VPS lane selects a runner that GitHub does not host. The image publish workflows MUST run on push only for `main`.

#### Scenario: Second workflow with the label

- **WHEN** a second workflow file names the self-hosted label
- **THEN** the repository test fails and names the file

#### Scenario: Approval setting differs

- **WHEN** the live fork approval setting is weaker than the recorded one
- **THEN** the plan lists the change, and an apply whose readback still differs exits non-zero

#### Scenario: Push to another branch

- **WHEN** a commit that changes an image is pushed to a branch other than `main`
- **THEN** no publish workflow runs

### Requirement: REQ-SEC-EIG-AGENT-SETTINGS — Keep hooks and shell allow entries out of the agent settings

A repository test MUST fail when the tracked agent settings file has a `hooks` key or a permission allow entry for a shell command. The test MUST allow only the schema, attribution and permission keys, and only file tool entries in the allow list.

#### Scenario: Hook added

- **WHEN** the settings file gains a `hooks` key
- **THEN** the test fails

#### Scenario: Current file

- **WHEN** the settings file has only attribution and file permission rules
- **THEN** the test passes
