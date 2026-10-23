# network/explicit-alternate-listeners Specification

## Purpose
Keep alternate public REALITY listeners an explicit operator choice across deployment layers.
## Requirements
### Requirement: REQ-ALT-OPT-IN — Disable implicit alternate listeners

Default runtime inputs, current provider examples and disposable CI listener
contracts MUST omit the alternate REALITY listener. An explicit nonzero alternate
MUST still render a matching server, firewall and client endpoint when selected.
Documentation MUST recommend independently reachable TCP/443 endpoints rather
than claiming that an alternate port is indistinguishable from ordinary HTTPS.

#### Scenario: Default deployment and delivery

- **WHEN** no alternate port is configured
- **THEN** no alternate REALITY listener or recipient endpoint is emitted

#### Scenario: Explicit alternate retained

- **WHEN** the operator declares a matching runtime alternate port and provider listener
- **THEN** the selected alternate remains usable and is included in appropriate checks

#### Scenario: Retained private listener contract is stale

- **WHEN** provider and runtime listener choices disagree after the default changes
- **THEN** existing preflight refuses the mismatch before host mutation
