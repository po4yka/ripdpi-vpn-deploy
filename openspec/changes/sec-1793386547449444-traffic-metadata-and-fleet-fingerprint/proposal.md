# Change: Close traffic-metadata retention and fleet-fingerprint audit findings

Task ID: `SEC-1793386547449444`

## Why

A read-only audit of the deployed node found that the server keeps a per-device
browsing ledger (Xray access log with sniffed destination names and device
identity, Hysteria connection records with client addresses) for up to two
weeks, which contradicts the threat model's "the device, not the node" promise.
It also found three fleet-wide fingerprints that do not depend on the transport
protocol: every deployment serves the byte-identical public-repository decoy
site and example XHTTP path, the XHTTP location answers probes differently from
the decoy site (Xray's bare 404, nginx's stock 502 when Xray is down), and the
borrowed REALITY identity is never checked against the node's own public
identities or DNS. Finally, the emitted sing-box client probes every transport
to the same address every five minutes through a well-known third-party URL.

## What Changes

- Xray renders `log.access: none` unless `vpn.enable_policy_ratelimit` is on, the only consumer of that log; Hysteria runs at `warn` log level so connection records never reach journald.
- BREAKING: production (`env: prod`) nginx-xhttp hosts must supply an operator-owned static site tree through `nginx_xhttp_public_site_dir`; the repository-bundled decoy remains available for staging, lab and Molecule hosts only.
- The committed secrets example no longer carries a deployable XHTTP path; strict validation refuses the placeholder.
- Both direct XHTTP locations intercept upstream errors and answer them with the decoy's ordinary 404, so a probe sees one site identity whether or not Xray is running.
- REALITY target validation requires X25519 and reports when a configured SNI name resolves to addresses outside the target's (borrowed) or outside the public endpoint (owned-public); self-steal refuses a shared hostname with a different certificate than nginx-xhttp.
- Emitted sing-box selectors test latency every 30 minutes instead of every 5.

## Capabilities

### New Capabilities

- `security/traffic-metadata-and-decoy-identity`: no per-connection transport metadata at rest by default, operator-owned decoy identity on production hosts, probe-consistent XHTTP error behaviour, REALITY identity consistency checks and a bounded client probe cadence.

### Modified Capabilities

- None.

## Impact

Ansible roles `xray`, `hysteria`, `nginx-xhttp`, `reality-self-steal`; `scripts/reality_target_validation.py`, `scripts/client_payload.py`; `secrets/prod.secrets.example.yaml`; `ansible/group_vars/all.yml`; snapshot goldens, unit tests and operator documentation. No Terraform, listener-contract, schema, credential or live-host change. Existing production hosts need the new site-tree override before their next deploy.
