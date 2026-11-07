## Purpose

Production rollouts reproduce from source without hand-set monitoring flags or out-of-repo firewall rules, and operator failures name their cause without exposing secrets.

## ADDED Requirements

### Requirement: REQ-SEC-RH-SELF-STEAL-SERIES — Derive self-steal certificate monitoring from the host

The agent MUST export the self-steal certificate expiry series whenever the self-steal certificate is installed on the node, without a separate profile flag. When the installed chain cannot be read, the agent MUST report certificate collection failure for that role.

#### Scenario: Installed certificate without profile flag

- **WHEN** the self-steal certificate is installed and the agent profile sets no self-steal flag
- **THEN** the agent exports the `role="reality-self-steal"` expiry series

### Requirement: REQ-SEC-RH-OBSERVER-EGRESS — Own the observer firewall additions

The Tailnet bootstrap foundation MUST render the observer private-ingress rule and, in Kuma Telegram mode, the container egress to the configured resolvers and the Telegram API network. Re-applying the foundation MUST NOT remove them. Telegram mode MUST be refused without valid egress inputs.

#### Scenario: Foundation re-applied in Telegram mode

- **WHEN** the foundation is rendered for the observer in Telegram mode
- **THEN** the forward chain contains the resolver DNS, Telegram HTTPS and return-path accepts

### Requirement: REQ-SEC-RH-OPERATOR-REFUSALS — Name operator failures without secrets

The observability operator MUST record the failing Ansible task name and host alias and nothing else from the task output. A busy node lock MUST refuse with a typed category that names the alias. A missing generated inventory MUST refuse with a typed category.

#### Scenario: Busy sentinel lock

- **WHEN** another run holds a node lock as a liveness sentinel
- **THEN** the run refuses with the busy category and names that node
