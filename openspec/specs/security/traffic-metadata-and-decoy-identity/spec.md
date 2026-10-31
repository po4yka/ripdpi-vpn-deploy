# security/traffic-metadata-and-decoy-identity Specification

## Purpose
Keep per-device traffic metadata off the node by default and remove the fleet-wide fingerprints that a public repository and a borrowed TLS identity create.

## Requirements

### Requirement: REQ-TMD-NO-LEDGER — No per-connection transport metadata by default

The rendered Xray frontend configuration MUST set `log.access` to `none` unless `vpn.enable_policy_ratelimit` is true, and the Hysteria service unit MUST set `HYSTERIA_LOG_LEVEL=warn`, so that neither device identity, client address nor destination name is written per connection.

#### Scenario: Default family profile

- **WHEN** a profile with `enable_policy_ratelimit: false` is rendered
- **THEN** the Xray configuration contains `"access": "none"` and the Hysteria unit carries `Environment=HYSTERIA_LOG_LEVEL=warn`.

#### Scenario: Policy rate-limiter enabled

- **WHEN** `vpn.enable_policy_ratelimit` is true
- **THEN** the Xray access log path is rendered so the daemon can tail it.

### Requirement: REQ-TMD-OWNED-DECOY — Production decoy content is operator-owned

The nginx-xhttp role MUST publish the static site from `nginx_xhttp_public_site_dir` when it is set, retiring the bundled pages that the operator tree does not provide, and MUST refuse convergence on a host whose inventory `env` is `prod` when that variable is empty. The committed secrets example MUST carry a `REPLACE_WITH_` placeholder for `xray.xhttp_path`.

#### Scenario: Production host without an operator tree

- **WHEN** `env` is `prod` and `nginx_xhttp_public_site_dir` is empty
- **THEN** the role fails before any host mutation and names the variable.

#### Scenario: Operator tree supplied

- **WHEN** `nginx_xhttp_public_site_dir` names a directory containing `404.html`
- **THEN** every regular file below it is published at the same relative path under `/var/www/public-site` and the bundled pages it does not contain are removed in the same transaction.

#### Scenario: Example path

- **WHEN** strict secrets validation runs on a document that still carries the example `xhttp_path`
- **THEN** validation refuses the unfilled placeholder.

### Requirement: REQ-TMD-PROBE-CONSISTENT — XHTTP errors look like the decoy

Both direct XHTTP locations MUST intercept upstream responses with status 404, 502, 503 or 504 and answer with HTTP 404 and the decoy's `404.html` body.

#### Scenario: Probe while Xray is down

- **WHEN** a client requests the XHTTP path while the loopback upstream is unreachable
- **THEN** nginx returns status 404 with the site's own error page, not a 502 page.

### Requirement: REQ-TMD-REALITY-CONSISTENCY — REALITY identity is checked for consistency

`reality_target_validation.py` MUST negotiate the TLS probe with X25519 only and report `x25519_unavailable` when the target cannot, MUST report `owned_name_resolution` in `owned-public` mode as `matches`, `elsewhere` or `unresolved` against the public endpoint's addresses (`not_applicable` for a borrowed target, which fails that comparison by construction), and the self-steal role MUST refuse a hostname shared with nginx-xhttp unless both roles carry the same certificate.

#### Scenario: Owned name that resolves elsewhere

- **WHEN** the owned name resolves to addresses disjoint from the public endpoint's
- **THEN** the report carries `owned_name_resolution: elsewhere`; no name or address is printed.

#### Scenario: Shared hostname with distinct certificates

- **WHEN** `reality_self_steal.server_name` equals `nginx_xhttp.server_name` and the PEM certificates differ while both roles are enabled
- **THEN** the self-steal role fails before host mutation.

### Requirement: REQ-TMD-CLIENT-CADENCE — Bounded client latency probing

The standard sing-box artifact's `urltest` group MUST use a 30-minute interval. The RIPDPI bundle MUST keep the cadence of the vendored contract fixtures until the paired client change lands.

#### Scenario: Standard artifact

- **WHEN** a sing-box document is emitted with at least one proxy outbound
- **THEN** its `auto` outbound has `interval` equal to `30m`.

#### Scenario: RIPDPI bundle

- **WHEN** a RIPDPI bundle is emitted
- **THEN** it stays byte-identical to the contract examples that the client vendors.
