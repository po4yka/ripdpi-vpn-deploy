# ansible/split-hop-live-tls-identity Specification

## Purpose
The live split-hop Node A serves real devices from a production address. This capability defines the TLS identity that its committed profile presents on that address, so that the profile passes the production TLS identity preflight without a recorded exception.

## Requirements

### Requirement: REQ-SHL-SELF-STEAL-IDENTITY — The live family-egress profile presents the operator certificate on TCP/443

The profile `vpn-split-hop-family-egress-live` MUST enable REALITY self-steal, so that a production host in this profile passes the TLS identity preflight with no `tls_identity_exception`. The profile MUST keep the family transports, the split-hop ingress scope, monitoring, watchdog and backup that it had before.

#### Scenario: Production preflight admits the live family-egress profile

- **WHEN** the TLS identity preflight evaluates the profile's `vpn` map for a production host with no `tls_identity_exception`
- **THEN** the preflight passes

#### Scenario: The other split-hop Node A profiles keep their layout

- **WHEN** the same preflight evaluates `vpn-split-hop-ingress-live`, `vpn-split-hop-ingress-staging` or `vpn-split-hop-family-egress-staging` for a production host
- **THEN** the preflight refuses, as it did before this change

#### Scenario: A host without the self-steal secret is refused before mutation

- **WHEN** a host in the live family-egress profile is deployed without a `reality_self_steal` secret, or with `xray.target` or `xray.server_names` that do not match the self-steal endpoint and name
- **THEN** the self-steal role refuses the deploy before it changes the host

### Requirement: REQ-SHL-SELF-STEAL-PORT — The self-steal endpoint stays private beside the public nginx-xhttp port

The profile MUST set `reality_self_steal_port` to a loopback port that is not one of its public TCP listeners and not an Xray or nginx-xhttp port, so that the role's port guard admits the profile with its default public nginx-xhttp port.

#### Scenario: The profile's self-steal port differs from its public ports

- **WHEN** the profile is rendered with the repository defaults for `xray_port`, `xray_fallback_port`, `nginx_xhttp_port`, `nginx_xhttp_public_port` and `nginx_xhttp_fallback_port`
- **THEN** `reality_self_steal_port` equals none of them

#### Scenario: Rollback restores the borrowed target

- **WHEN** the operator reverts this change and redeploys the host with its previous secrets
- **THEN** the self-steal role retires its owned endpoint and the production preflight refuses the host again unless an exception is recorded
