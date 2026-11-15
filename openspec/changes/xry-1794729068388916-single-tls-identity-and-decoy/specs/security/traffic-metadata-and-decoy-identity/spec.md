## ADDED Requirements

### Requirement: REQ-TMD-SELF-STEAL-OWNED-DECOY — The self-steal site is operator-owned on production

The self-steal role MUST publish its static site from `reality_self_steal_public_site_dir` when that variable is set, and MUST remove bundled pages that the operator tree does not provide. It MUST refuse convergence on a host whose inventory `env` is `prod` when the variable is empty.

#### Scenario: Production host without an operator tree

- **WHEN** `env` is `prod`, self-steal is enabled and `reality_self_steal_public_site_dir` is empty
- **THEN** the role fails before it changes the host and names the variable

#### Scenario: Operator tree supplied

- **WHEN** the variable names a directory that contains `index.html` and `404.html`
- **THEN** the files below it are published and no bundled page stays on the host

#### Scenario: Non-production host

- **WHEN** `env` is not `prod` and the variable is empty
- **THEN** the role publishes the bundled site

### Requirement: REQ-TMD-SINGLE-IDENTITY — One TLS identity for each public address on production

On a host whose inventory `env` is `prod`, the transport preflight MUST refuse a borrowed REALITY target when Hysteria or nginx-xhttp is enabled on the same address, on any port, or when the operator recorded `reality_target_network: different_asn`, unless `tls_identity_exception` records a non-empty reason. The preflight MUST NOT contact a lookup service.

#### Scenario: Borrowed target beside Hysteria on UDP/443

- **WHEN** `env` is `prod`, REALITY uses a borrowed target, Hysteria listens on UDP/443 of the same address, and no exception is recorded
- **THEN** preflight fails before any host mutation, names the two listeners and names the three ways to pass

#### Scenario: Borrowed target recorded in a different network

- **WHEN** `env` is `prod`, REALITY uses a borrowed target without another listener, and `reality_target_network` is `different_asn`
- **THEN** preflight fails before any host mutation

#### Scenario: Borrowed target without a recorded network

- **WHEN** `env` is `prod`, REALITY uses a borrowed target without another listener, and `reality_target_network` is empty, `unknown` or `same_asn`
- **THEN** preflight passes

#### Scenario: Self-steal beside the operator listeners

- **WHEN** self-steal is enabled and Hysteria and nginx-xhttp are enabled
- **THEN** preflight passes, because every listener presents an operator-owned name

#### Scenario: Non-production host

- **WHEN** `env` is not `prod`
- **THEN** preflight passes for every layout

#### Scenario: Recorded exception

- **WHEN** `tls_identity_exception` holds a reason
- **THEN** preflight passes and the node manifest records that an exception is active, without the reason text

### Requirement: REQ-TMD-PORT-80-DECOY — Port 80 behaves like the decoy site

A port 80 server MUST NOT redirect to a port other than 443. When the HTTPS port of a configured name is not 443, port 80 MUST serve the decoy site for that name. A request whose Host is not a configured server name MUST receive the decoy `404.html` with status 404. These rules apply to the primary name, a distinct fallback name and the managed-TLS port 80 server.

#### Scenario: Non-443 XHTTP port

- **WHEN** the XHTTP public port is 8443 and a client requests `/` on port 80 with the configured Host
- **THEN** nginx returns the decoy index with status 200 and no `Location` header

#### Scenario: Unknown Host

- **WHEN** a client requests port 80 with the node address as Host
- **THEN** nginx returns status 404 with the decoy error page

#### Scenario: XHTTP on 443

- **WHEN** the XHTTP public port is 443
- **THEN** port 80 redirects the configured Host to `https://` with no port
