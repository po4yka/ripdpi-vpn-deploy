# role: egress-proxy — CONNECT-only provider API proxy

## Design decisions

Debian `squid`, pinned to the exact package version, because a custom proxy would be new code on a security boundary and tinyproxy cannot refuse non-CONNECT methods for allowlisted hosts. The ACL order is the contract: `deny !CONNECT`, `deny !SSL_ports` (443), `deny !api`, `allow ci_src`, `deny all`. No `ssl_bump` and `cache deny all`: the node never terminates or stores TLS.

The `api` ACL is `dstdomain -n`: squid compares the literal target text and never reverse-resolves, so an IPv4 or IPv6 literal (even the address of an allowlisted name, or one with an allowlisted PTR) is denied before any upstream connection. The OpenTofu state backend is S3 with path-style addressing, so the one extra host is its endpoint (`egress_proxy_state_host`, for example `s3.fr-par.scw.cloud`); the role refuses an empty value or an IP. No B2 host: nothing that uses the proxy talks to B2.

The listen address is a required input. In production (`egress_proxy_require_tailnet_listen: true`) it must be a canonical dotted-quad inside 100.64.0.0/10 (no leading zeros, `\Z`-anchored); only Molecule turns that off and uses loopback. The node holds no secrets, and the access log records time, client, target host, status, bytes and squid result code (no URL, no headers). `client_ip_max_connections` is 64: far below the 4096 descriptor budget (two per tunnel) yet above a CI runner's concurrent provider calls. ICP, HTCP, SNMP and the pinger are off; the `acl CONNECT method CONNECT` is declared explicitly.

The packaged unit is hardened by a drop-in. It runs squid as `proxy` from the start (`User=proxy`, empty `CapabilityBoundingSet`, port 3128 is unprivileged), so squid never needs setuid. `pid_filename none` plus `PIDFile=` reset avoids a root-owned pid path under `ProtectSystem=strict`. The packaged logrotate fragment signals squid only when `/run/squid.pid` exists, so with no pid file it would never reopen logs; the role replaces it with `files/squid-logrotate`, which sends USR1 through `systemctl kill` (squid has `logfile_rotate 0`, logrotate owns rotation). Molecule proves a forced rotation moves old lines to `access.log.1` and new requests land in the new file. Squid 6.13 reports `dns_v4_first` as obsolete, so it is not set; the Terraform root disables IPv6 (`ipv6_enabled = false`), so the node has no public IPv6 source address. `After=tailscaled.service` orders the bind after the Tailnet address exists; `Restart=on-failure` covers a slow Tailnet.

Firewall: this role opens nothing. The playbook that applies it, `ansible/playbooks/egress-proxy.yml` (guarded by `tests/unit/test_egress_proxy_playbook.py`), sets `firewall_tailnet_extra_tcp_ports: [3128]` on the `firewall` role (accepts the port only on `tailscale0` from 100.64.0.0/10; the firewall default-drops everything else). The role is not in `site.yml` and has no `vpn.enable_*` toggle; it runs from that playbook, which derives `egress_proxy_listen_address` from `tailscale status --json` and requires `tag:egress` (see `docs/how-to/egress-proxy.md`).

## What's done well

- Denials are proved against a running squid with raw sockets, not by reading the config.
- The package pin, listener and allowlist are role defaults, so a change is a reviewed diff.

## Pitfalls

- Bumping `egress_proxy_package_version` needs the exact Debian version string (`apt-cache policy squid`); a missing version fails the install rather than drifting.
- Do not add `.domain` wildcard entries to `egress_proxy_api_hosts`: the validator rejects them, because they widen the allowlist to every subdomain.
- Molecule cannot prove the upstream path: allowlisted CONNECTs prove only a non-ACL outcome (200, 502 or 503; the container may have no route out). Provider-through-proxy proof is the W5 live step.
- A squid upgrade can obsolete a directive; the `squid -k parse` validate step catches that at converge time.
- Exposure floor: `systemd-analyze security squid.service` measures 3.0 (OK) and Molecule fails above `egress_proxy_exposure_floor: 3.0` in `verify.yml`. Raise the floor only with a stated reason.
- The `-n` proof maps 198.51.100.7 to `api.vultr.com` in `/etc/hosts` before squid starts; without `-n` squid would match that literal through the hosts mapping.
- The squid.conf golden renders with an empty listen address and state host: `render-snapshots.py` has one shared variable set and no per-template input. The admission test (`tests/unit/test_egress_proxy_admission.py`) covers real values.

## Accepted risks

- No TLS inspection by design: a CDN-fronted allowlisted host can carry another SNI or virtual host over the same CONNECT tunnel. The allowlist limits destinations, not the content inside the tunnel.
- The package pin must be bumped when a Debian security update supersedes it. Until then fresh installs and unattended upgrades fail closed (the pinned version is no longer installable or is held), which stops the node rather than running an unreviewed build.
