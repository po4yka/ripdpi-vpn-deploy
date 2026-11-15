## ADDED Requirements

### Requirement: REQ-PROTO-RTV-NETWORK — Report whether the target and the node share a network

For a borrowed target, `reality_target_validation.py` MUST report `target_network` as `same_asn`, `different_asn` or `unknown`, from the ASN of each resolved target address and the ASN of the node's public address. It MUST report `not_applicable` in `owned-public` mode. It MUST NOT print a name, an address or an ASN number.

#### Scenario: Target in another network

- **WHEN** every resolved target address has an ASN that differs from the node's ASN
- **THEN** the report carries `target_network: different_asn`

#### Scenario: Lookup failure

- **WHEN** the ASN lookup fails for the node or for the target
- **THEN** the report carries `target_network: unknown` and the validator does not fail for that reason

#### Scenario: Owned target

- **WHEN** the validator runs in `owned-public` mode
- **THEN** the report carries `target_network: not_applicable`
