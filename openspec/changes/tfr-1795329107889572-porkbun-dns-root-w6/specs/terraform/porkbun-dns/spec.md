## Purpose

Define how DNS records of the fleet's Porkbun domains are managed as an OpenTofu root with a vetted pinned provider, encrypted remote state, a record policy and API access limited per domain, permission and source address.

## ADDED Requirements

### Requirement: REQ-PORKBUN-PROVIDER — One vetted provider at one exact version

The root MUST use one community Porkbun provider pinned to an exact version and locked with hashes for every CI and operator platform. The vetting record MUST name the release reviewed, its license, maintainer activity, and that its HTTP client honours `HTTPS_PROXY` and sends credentials only to the Porkbun API host.

#### Scenario: Version range

- **WHEN** `versions.tf` uses `~>` or `>=` for the Porkbun provider
- **THEN** the toolchain-pin test fails

### Requirement: REQ-PORKBUN-SCOPE — Only managed domains are touched

The root MUST manage records only for domains listed in `managed_domains`. A record for any other domain MUST be refused by policy before apply. TTLs MUST be at least 600 seconds.

#### Scenario: Unlisted domain

- **WHEN** tfvars add a record for a domain not in `managed_domains`
- **THEN** `make tf-conftest PROVIDER=porkbun` fails and names the record

### Requirement: REQ-PORKBUN-ACCESS — API access is per domain, per permission and per address

API access MUST be enabled only for managed domains. The apply key MUST have DNS permission and the plan key read permission, both limited to the managed domains and to the egress address when Porkbun accepts a source restriction.

#### Scenario: Call from another address

- **WHEN** the apply key is used from a runner address that is not the egress address
- **THEN** Porkbun rejects the call

### Requirement: REQ-PORKBUN-IMPORT — Adoption changes nothing

Before the first apply, every existing record of each managed domain MUST be imported, and `tofu plan` MUST show no changes. A domain whose plan is not empty MUST NOT be applied.

#### Scenario: Unmanaged record found

- **WHEN** the import list misses a live record
- **THEN** the plan shows a delete or no-op mismatch and the adoption of that domain stops
