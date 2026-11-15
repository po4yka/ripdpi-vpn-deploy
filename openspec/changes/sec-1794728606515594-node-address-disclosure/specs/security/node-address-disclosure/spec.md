## Purpose

Node addresses and hostnames stay out of third-party services, cleartext lookups, the Git worktree and tracked files unless the operator makes an explicit choice.

## ADDED Requirements

### Requirement: REQ-SEC-NAD-PRIVATE-ALERTS — Send node alerts only to an operator-chosen destination

The watchdog MUST send no notification when the operator configured no destination. A production host MUST refuse the public notification service as the destination. Alert titles and tags MUST identify the node by its alias and MUST NOT contain the hostname. Notification tokens and topics MUST NOT appear in process arguments.

#### Scenario: Default profile

- **WHEN** a host is deployed with the default watchdog variables
- **THEN** the rendered notification configuration has no destination and the watchdog sends no request to a notification service

#### Scenario: Public service on production

- **WHEN** `env` is `prod` and the notification URL is the public notification service
- **THEN** the role fails before it changes the host

#### Scenario: Public service on a named production workspace

- **WHEN** `env` is the workspace name, `vpn_build_environment` is `prod` and the notification URL is the public notification service
- **THEN** the role fails before it changes the host

#### Scenario: Alert content

- **WHEN** the watchdog sends an alert to a configured destination
- **THEN** the title and tags contain the node alias and no hostname

#### Scenario: Token in the process list

- **WHEN** an operator script sends a notification with a token
- **THEN** the token and the topic are absent from the argument list of every child process

### Requirement: REQ-SEC-NAD-BURN-CHECK-LOCAL — Keep the scheduled burn check off third-party vantage points

The burn check MUST NOT submit a node address to a third-party probe service and MUST NOT send a UDP probe unless the operator passes an explicit option on that run. The installed scheduled entry MUST NOT pass that option.

#### Scenario: Scheduled run

- **WHEN** the installed cron entry runs the burn check
- **THEN** no request leaves for a third-party probe service and no UDP probe is sent

#### Scenario: Manual third-party run

- **WHEN** the operator runs the burn check with the explicit third-party option
- **THEN** the check uses the vantage points that the operator named

#### Scenario: Environment override without the option

- **WHEN** only the vantage-point environment variable is set
- **THEN** the burn check refuses to use a third-party service

### Requirement: REQ-SEC-NAD-ENCRYPTED-LOOKUPS — Keep node addresses out of cleartext lookups

A scheduled reputation or ASN lookup MUST carry the node address only over an encrypted transport. When no encrypted transport is available, the lookup MUST fail closed and report that it did not run.

#### Scenario: Reputation lookup

- **WHEN** the scheduled reputation check queries a block list for a node address
- **THEN** the query leaves over an encrypted resolver transport

#### Scenario: Encrypted transport unavailable

- **WHEN** the encrypted resolver cannot be reached
- **THEN** the check exits non-zero and sends no cleartext query

### Requirement: REQ-SEC-NAD-PRIVATE-REPORTS — Write node reports outside the worktree

A script that stores output from a node MUST write it to the private operator state directory with mode `0600`. The file name MUST NOT contain a node address.

#### Scenario: Probing summary

- **WHEN** the probing summary stores a report
- **THEN** the file is outside the repository, has mode `0600`, and its name has no address

### Requirement: REQ-SEC-NAD-TRACKED-ADDRESS-GUARD — Refuse public addresses in tracked files

A repository test MUST fail when a tracked text file contains a globally routable IPv4 or IPv6 address literal that is not in the committed list of well-known public service addresses. Documentation ranges and the redaction placeholder MUST pass.

#### Scenario: Node address in a verification note

- **WHEN** a tracked Markdown file contains a globally routable address that is not in the list
- **THEN** the test fails and names the file and line

#### Scenario: Documentation range

- **WHEN** a tracked file contains an address from a documentation range
- **THEN** the test passes
