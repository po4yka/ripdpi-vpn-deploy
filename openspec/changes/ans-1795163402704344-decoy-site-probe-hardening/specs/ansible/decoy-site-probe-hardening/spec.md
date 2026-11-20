## Purpose

The nginx-xhttp and reality-self-steal roles publish the web sites that an outside probe sees on a node. This capability defines which operator-owned content the roles refuse and how the sites answer TLS and HTTP probes, so that a probe cannot link two nodes by content or tell a node from an ordinary web site by its TLS behaviour.

## ADDED Requirements

### Requirement: REQ-DSP-BUNDLED-BYTES — An operator-owned site repeats no repository-bundled file

The nginx-xhttp and reality-self-steal roles MUST refuse an operator-owned site tree that contains a regular file whose bytes equal a file under either role's `files/public-site/` directory. The refusal MUST occur before the role stages the publication and MUST NOT depend on `env` or `vpn_build_environment`.

#### Scenario: A copied bundled file is refused under any label

- **WHEN** the operator-owned tree of either role contains a copy of a bundled file, under any file name, and `env` is `prod` or `staging`
- **THEN** the role fails, names the file and the site directory variable, and stages nothing

#### Scenario: A tree with its own content is published

- **WHEN** the operator-owned tree contains only files that differ from every bundled file
- **THEN** the role stages the tree as before

### Requirement: REQ-DSP-DOT-PATHS — Dot paths of the operator-owned tree stay on the controller

Both roles MUST NOT publish a file or directory of the operator-owned tree whose relative path has a component that starts with a dot, except the component `.well-known`.

#### Scenario: A checkout is used as the site tree

- **WHEN** the tree contains `.git/config`, `.htpasswd` and `.well-known/security.txt`
- **THEN** the role publishes `.well-known/security.txt` and neither of the other two files

### Requirement: REQ-DSP-TLS-DEFAULT-SERVER — A handshake that does not name the site receives no certificate

The nginx-xhttp vhost MUST declare one default TLS server for each TLS port that it serves. That server MUST refuse a handshake without SNI or with a name that no server owns, MUST hold no certificate, and MUST answer a request that arrives with the right SNI and another Host with status 404 and the site 404 page. It MUST NOT proxy to Xray.

#### Scenario: The node address is scanned

- **WHEN** a client completes TCP to the TLS port and sends a ClientHello without SNI or with a foreign name
- **THEN** nginx sends the `unrecognized_name` alert and no certificate

#### Scenario: The right SNI carries another Host

- **WHEN** a client sends the owned SNI and a `Host` header that is not the owned name, for any path that includes the XHTTP path
- **THEN** the response is status 404 with the site 404 page

### Requirement: REQ-DSP-TLS-POLICY — The sites accept what an ordinary site accepts

Every TLS server of both roles MUST accept TLS 1.2 and TLS 1.3, MUST offer the groups X25519, prime256v1 and secp384r1 with X25519 first, and MUST limit TLS 1.2 to ECDHE AEAD ciphers. Session tickets MUST stay off.

#### Scenario: A TLS 1.2 client connects

- **WHEN** a client offers only TLS 1.2 with the owned SNI
- **THEN** the handshake completes with an ECDHE cipher

#### Scenario: A REALITY client connects

- **WHEN** a client offers TLS 1.3 with X25519 only to the self-steal target
- **THEN** the handshake completes

### Requirement: REQ-DSP-TARGET-LIMITS — The self-steal target holds more idle connections than the packaged limit

The self-steal role MUST publish the main nginx configuration with `worker_connections` equal to `reality_self_steal_worker_connections` (default 8192) and `worker_rlimit_nofile` equal to twice that value. It MUST validate the edited file with nginx before it replaces the original, and MUST NOT add the file to the paths of its nginx transaction.

#### Scenario: The role converges

- **WHEN** the role converges on a host with the packaged `nginx.conf`
- **THEN** the running workers have the raised limits and a second run changes nothing

### Requirement: REQ-DSP-CERT-LIFETIME — A certificate close to expiry is refused

The self-steal role MUST refuse a certificate that has fewer than `reality_self_steal_min_cert_lifetime_days` days left. The default MUST be 30.

#### Scenario: Default lifetime

- **WHEN** the role converges with the default variable and a certificate that expires in 20 days
- **THEN** the role fails before it stages the publication

#### Scenario: A certificate with enough lifetime

- **WHEN** the certificate expires in 45 days
- **THEN** the lifetime check passes

### Requirement: REQ-DSP-HTTP-REDIRECT — The self-steal TCP/80 redirect is opt-in and follows the listener contract

With `reality_self_steal_http_redirect` true the self-steal vhost MUST redirect TCP/80 requests for the owned name to HTTPS and MUST answer any other Host with the site 404, unless nginx-xhttp on the same host already owns those servers. The role MUST refuse the option when the public listener contract has no enabled TCP/80. With the default false the role MUST add no TCP/80 listener.

#### Scenario: The option is off

- **WHEN** the vhost renders with defaults
- **THEN** it contains no `listen 80`

#### Scenario: The option is on beside nginx-xhttp with another name

- **WHEN** the vhost renders with the option and nginx-xhttp enabled for another hostname
- **THEN** it contains the named redirect server and no second default server

### Requirement: REQ-DSP-XHTTP-EDGE — The XHTTP edge keeps idle streams and one error identity

The XHTTP locations MUST allow a request body, an upstream read and an upstream send to stay idle for at least 3600 seconds, and MUST answer upstream statuses 400, 401, 403, 404, 405, 408, 409, 413, 429, 500, 501, 502, 503 and 504 with status 404 and the site 404 page. The ACME HTTP server MUST answer a missing challenge file with the site 404 page. The routing-list base URL MUST omit the port when the public port is 443.

#### Scenario: Xray answers 429

- **WHEN** the upstream answers a request on the XHTTP path with status 429
- **THEN** the client receives status 404 with the site 404 page

#### Scenario: The public port is 443

- **WHEN** the routing-list policy renders for public port 443
- **THEN** its base URL has no port
