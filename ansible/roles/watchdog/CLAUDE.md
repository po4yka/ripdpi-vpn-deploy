# role: watchdog — self-healing service supervision

## Design decisions

**Two-level supervision** — systemd is layer 1 (Restart=on-failure). The
watchdog role adds layer 2: a timer that records unit, listener, and
configuration diagnostics and performs an authenticated VLESS+REALITY request
through every configured listener to an operator-owned HTTPS endpoint with an exact expected status.

**Dedicated probe identity** — `watchdog.reality_probe_client` names a unique
entry in `xray.clients`. Never reuse a recipient device credential.
Multi-cohort deployments authorize that identity in every cohort so a green
result covers every REALITY listener.

**Service endpoint is not the SSH endpoint** — the rendered client targets
`vpn_service_address`, which inventory derives from Terraform's public IPv4.
Overriding `ansible_host` for Tailscale administration must never redirect a
data-plane probe onto the management path.

**Bounded recovery** — failures must cross `fail_threshold` before the watchdog
restarts only the transport units whose probes failed. Restart attempts remain
capped by `kicks_per_hour_max`, notifications by `alerts_per_hour_max`, and a
red probe run exits non-zero so systemd and external checks retain the signal.

**Bounded probe cleanup** — the temporary Xray client receives TERM first, then
KILL after a short deadline. A wedged probe process must never hold the systemd
oneshot open indefinitely.

## What's done well

- **Protocol completion is load-bearing** — the configured exact HTTP status returned through the temporary
  SOCKS client proves the configured UUID, short ID, REALITY key/SNI, listener,
  and outbound request path completed.
- **Probe secrets stay root-only** — the generated Xray client config is `0600`;
  credentials never enter the environment file, command line, journal, or alert
  body.
- **Cleanup is unconditional** — the temporary Xray client is terminated after
  success, failure, startup timeout, or signal, with a bounded TERM-to-KILL
  escalation.

## Pitfalls

- **The canary is part of the contract** — it must be operator-owned, have valid public TLS, and return `watchdog_secrets.reality_probe_expected_status` (default `204`). A normal public site root can use `200` without exposing a dedicated health endpoint. Canary failure correctly makes the
  protocol signal red.
- **On-node is not outside-in** — self-dialing the public listener validates
  protocol configuration but cannot detect transit filtering that affects other
  networks. Rotation still requires an independent external client-path quorum.
- **A partial listener outage is a failure** — primary, fallback, and every
  cohort listener are all probed; one red listener increments the common
  consecutive-failure counter.
- **Inventory must preserve both addresses** — `make inventory` emits
  `vpn_service_address` beside `ansible_host`. Local SSH overrides may replace
  only the latter.
