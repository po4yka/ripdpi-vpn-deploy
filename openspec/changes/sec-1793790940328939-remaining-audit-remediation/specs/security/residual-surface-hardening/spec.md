## Purpose

Remaining audit findings and residual risks from the medium remediation are closed in source.

## ADDED Requirements

### Requirement: REQ-SEC-RSH-DNS-POLICY-RECORDS — Publish mail and certificate authority policy records

The Vultr root MUST accept quoted printable TXT records, CAA `issue`, `issuewild` and `iodef` records, and underscore labels. It MUST reject an unquoted TXT value, an unknown CAA tag and a repeated TXT or CAA record.

#### Scenario: DMARC and CAA records

- **WHEN** `managed_dns_records` contains `_dmarc` TXT and two apex CAA records
- **THEN** the plan accepts them

#### Scenario: Malformed CAA tag

- **WHEN** a CAA record uses the tag `issuer`
- **THEN** plan fails validation

### Requirement: REQ-SEC-RSH-EMBEDDED-IPV4-DENY — Refuse destinations that embed or benchmark addresses

The recipient policy, the AWG forward drop set and the gateway answer filter MUST deny `198.18.0.0/15`, `64:ff9b::/96` and `2002::/16`.

#### Scenario: NAT64 address of a private IPv4 target

- **WHEN** a recipient requests `64:ff9b::a01:203`
- **THEN** the policy refuses it

### Requirement: REQ-SEC-RSH-XRAY-SANDBOX — Sandbox the production Xray unit

The Xray unit MUST meet the transport sandbox baseline: `MemoryDenyWriteExecute`, the `@system-service` syscall allowlist without `@privileged` and `@resources`, restricted address families, and no write access to its configuration directory.

#### Scenario: Unit render

- **WHEN** the Xray unit template renders
- **THEN** it carries every baseline directive and its writable paths exclude the configuration directory

### Requirement: REQ-SEC-RSH-SELF-STEAL-EXPIRY — Alert before the self-steal certificate expires

When REALITY self-steal is enabled, the node MUST export the expiry of the installed self-steal certificate, so that the existing certificate expiry alerts fire before it expires.

#### Scenario: Certificate near expiry

- **WHEN** the installed self-steal certificate is inside the warning window
- **THEN** the certificate expiry warning fires for that node

### Requirement: REQ-SEC-RSH-RELAY-DROPS — Signal samples dropped after relay acceptance

The collector MUST scrape the relay's drop counters on loopback and alert when they increase.

#### Scenario: Prometheus rejects relayed samples

- **WHEN** the relay drop counter increases
- **THEN** the relay drop alert fires
