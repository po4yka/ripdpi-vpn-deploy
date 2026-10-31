## Purpose

Keep per-device traffic metadata off the node by default: the public decoy vhosts log no client identity and monitoring retains their logs for a bounded period.

## ADDED Requirements

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
