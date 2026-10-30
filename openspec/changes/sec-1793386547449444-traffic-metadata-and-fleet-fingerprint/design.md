## Context

The audit (read-only, origin/main 6297d20) traced what the node retains and what a prober sees. The transport-egress gateway already logs nothing per connection; the Xray frontend and Hysteria still do. The decoy site, its assets and the example XHTTP path live in the public repository and are deployed verbatim. REALITY validation covers TLS 1.3, H2 and SAN but not key share or DNS consistency.

## Goals / Non-Goals

- Goal: no per-connection ledger on a default node; a production decoy that is unique per operator; one site identity for every probe outcome; validator evidence for the identity heuristics; a slower client probe.
- Non-goal: encrypted DNS from the gateway, access-log changes for the decoy site, Hysteria port moves, automatic target failover, per-device uTLS or Hysteria bandwidth variation (audit items 7 to 13).

## Decisions

- Xray access log follows `vpn.enable_policy_ratelimit` through a role default `xray_access_log_enabled`; the watchdog's `policy_reject_spike` detector already tolerates an empty log. Rejected: moving logrotate into the xray role (the stanza depends on the egress recovery helper owned by monitoring's install path).
- Hysteria log level is an `Environment=` line in the unit, not a config key, so the YAML validator contract is untouched.
- Operator site trees are read on the controller with `ansible.builtin.find` (delegated, `file_type: file`) and encoded through `base64` on the controller, because the `file` lookup cannot carry binary assets; rows join the existing compensated nginx transaction, and bundled page paths missing from the tree are declared `absent` so an identity swap is atomic. The refusal is keyed on inventory `env == 'prod'`, the same key the snell and hysteria-realm roles use. Rejected: an acknowledgement toggle (it would be set once and forgotten).
- `proxy_intercept_errors on` plus `error_page 404 502 503 504 =404 /404.html` in both XHTTP locations; headers stay at server scope as the role note requires.
- The validator's TLS worker calls `set_ecdh_curve("X25519")`; a handshake failure under that constraint is reported as `x25519_unavailable`. DNS consistency reuses the existing `dns` worker per configured name. Self-steal compares PEM text for the shared hostname instead of forbidding it, because one identity on every port is the stronger posture.
- `urltest.interval` becomes `30m`; the URL stays the sing-box default because the operator-owned probe contract (`client_payload_failover`) already covers verified payload probing.

## Contracts and ownership

- Ansible: `roles/xray/{defaults,templates/config.json.j2}`, `roles/hysteria/templates/hysteria-server.service.j2`, `roles/nginx-xhttp/{defaults,tasks/enable.yml,templates/site.conf.j2}`, `roles/reality-self-steal/tasks/main.yml`, `group_vars/all.yml` (`nginx_xhttp_public_site_dir`).
- Scripts: `reality_target_validation.py`, `client_payload.py`.
- Secrets: example only (`xray.xhttp_path` placeholder); schema unchanged.
- Fixtures: snapshot goldens, kill-switch fixture, bundle contract examples that carry the interval.

## Risks / Trade-offs

- Lost blackhole-spike detection without policy-ratelimit → documented; the detector still runs when the log exists.
- Existing production hosts fail the next deploy until the operator supplies a site tree → stated as BREAKING with the migration below.
- Validator DNS lookups add bounded network calls per name → the existing per-stage and aggregate budgets cover them.

## Migration Plan

Forward: set `nginx_xhttp_public_site_dir` in the same private extra-vars file that carries `public_site_canonical_url`, pointing at a directory with at least `404.html`; replace `/app-sync` in SOPS with a private path and re-emit clients; redeploy. Rollback: revert the commit; the nginx transaction restores prior site bytes. No provider or schema migration.
