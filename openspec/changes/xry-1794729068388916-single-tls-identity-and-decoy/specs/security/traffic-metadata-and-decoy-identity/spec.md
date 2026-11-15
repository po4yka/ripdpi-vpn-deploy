## ADDED Requirements

### Requirement: REQ-TMD-SELF-STEAL-OWNED-DECOY — The self-steal site is operator-owned on production

The self-steal role MUST publish its static site from `reality_self_steal_public_site_dir` when that variable is set, and MUST remove bundled pages that the operator tree does not provide. It MUST refuse convergence on a host whose inventory `env` is `prod` when the variable is empty.

#### Scenario: Production host without an operator tree

- **WHEN** `env` is `prod`, self-steal is enabled and `reality_self_steal_public_site_dir` is empty
- **THEN** the role fails before any host mutation and names the variable

#### Scenario: Operator tree supplied

- **WHEN** the variable names a directory that contains `index.html` and `404.html`
- **THEN** the files below it are published and no bundled page stays on the host

#### Scenario: Non-production host

- **WHEN** `env` is not `prod` and the variable is empty
- **THEN** the role publishes the bundled site

### Requirement: REQ-TMD-SINGLE-IDENTITY — One TLS identity for each public address on production

On a host whose inventory `env` is `prod`, the transport preflight MUST refuse a layout in which one public address presents two unrelated TLS identities, unless `tls_identity_exception` records a non-empty reason. Two identities are unrelated when REALITY on TCP/443 uses a borrowed target and another enabled listener on the same address presents the operator certificate, or when the validator reported the borrowed target in a different network from the node.

#### Scenario: Borrowed target beside Hysteria on UDP/443

- **WHEN** `env` is `prod`, REALITY uses a borrowed target, Hysteria listens on UDP/443 of the same address, and no exception is recorded
- **THEN** preflight fails before any host mutation and names the two listeners

#### Scenario: Self-steal with a shared certificate

- **WHEN** self-steal is enabled and Hysteria and nginx-xhttp use the same certificate as the self-steal site
- **THEN** preflight passes

#### Scenario: Recorded exception

- **WHEN** `tls_identity_exception` holds a reason
- **THEN** preflight passes and the node manifest records that an exception is active, without the reason text

### Requirement: REQ-TMD-PORT-80-DECOY — Port 80 behaves like the decoy site

The port 80 server MUST NOT redirect to a port other than 443. When the XHTTP public port is not 443, port 80 MUST serve the decoy site. A request whose Host is not the configured server name MUST receive the decoy `404.html` with status 404.

#### Scenario: Non-443 XHTTP port

- **WHEN** the XHTTP public port is 8443 and a client requests `/` on port 80 with the configured Host
- **THEN** nginx returns the decoy index with status 200 and no `Location` header

#### Scenario: Unknown Host

- **WHEN** a client requests port 80 with the node address as Host
- **THEN** nginx returns status 404 with the decoy error page

#### Scenario: XHTTP on 443

- **WHEN** the XHTTP public port is 443
- **THEN** port 80 redirects the configured Host to `https://` with no port
