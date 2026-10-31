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

### Requirement: REQ-TMD-DECOY-LOG-ANON — Decoy access logs carry no client identity

The rendered nginx-xhttp primary and fallback vhosts and the rendered reality-self-steal vhost MUST write their access logs through a named `log_format` whose layout references no client address (`$remote_addr`, `$binary_remote_addr`, `$realip_remote_addr`, `$proxy_protocol_addr`, `$http_x_forwarded_for`), no `$remote_user`, no `$http_referer` and no `$http_user_agent`, and MUST NOT use nginx's default `combined` format for any enabled access log.

#### Scenario: Primary and fallback public vhosts

- **WHEN** the nginx-xhttp site template is rendered with `fallback_enabled: true`
- **THEN** both `access_log /var/log/nginx/vpn-xhttp*.access.log` directives name the role's anonymous format and that format's layout contains none of the listed variables.

#### Scenario: Loopback self-steal vhost

- **WHEN** the reality-self-steal site template is rendered
- **THEN** `access_log /var/log/nginx/reality-self-steal.access.log` names the role's anonymous format with the same property.

#### Scenario: Transport and bearer surfaces stay silent

- **WHEN** the nginx-xhttp template is rendered with and without the fallback host
- **THEN** every `access_log` directive is either `off` or names `vpn_public`; no directive falls back to the default format.

#### Scenario: Both roles on one host

- **WHEN** nginx-xhttp and reality-self-steal are both enabled on a node
- **THEN** the two site files declare differently named formats, so `nginx -t` accepts the combined configuration.

### Requirement: REQ-TMD-DECOY-LOG-STATUS-FIELD — Status consumers keep reading the anonymous format

The `vpn_public` and `vpn_self_steal` formats MUST keep the `combined` field layout, with the removed fields replaced by `-` placeholders, so that `"$request" $status` stays adjacent and `$status` remains the ninth whitespace-separated field of a well-formed request line. The watchdog `nginx_403_spike` detector MUST count a 403 line written in that format.

#### Scenario: Watchdog counts a 403 in the anonymous format

- **WHEN** the detector's `awk` program from the rendered `vpn-watchdog.sh` runs over lines produced by the rendered nginx-xhttp format with statuses 403, 200 and 403
- **THEN** it reports 2.

#### Scenario: Native endpoint check still matches the request line

- **WHEN** a request is served by the rendered vhost
- **THEN** the log line contains `"<method> <path> <protocol>" <status>` in that order.

### Requirement: REQ-TMD-NGINX-LOG-RETENTION — Bounded nginx log retention

The monitoring role's `/etc/logrotate.d/nginx` policy MUST rotate `/var/log/nginx/*.log` daily and keep at most 7 rotations.

#### Scenario: Rendered policy

- **WHEN** `logrotate-nginx.j2` is rendered with the default variables
- **THEN** the stanza contains `daily` and `rotate 7` and still covers `/var/log/nginx/*.log` as the single owner.

#### Scenario: Rollback

- **WHEN** the change is reverted and the roles redeploy
- **THEN** the previous site files and logrotate policy are restored through the same transactions; already written anonymous lines remain readable by the status-field consumers.
