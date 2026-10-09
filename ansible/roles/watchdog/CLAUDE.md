# role: watchdog — self-healing service supervision

## Design decisions

**Server validation uses the installed runtime environment** — the shared Xray validator resolves `XRAY_LOCATION_ASSET` from the loaded Xray unit before testing its server configuration, including bundled-asset profiles. Canary client invocation remains separate.

**Two-level supervision** — systemd is layer 1 (Restart=on-failure). The
watchdog role adds layer 2: a timer that records unit, listener, and
configuration diagnostics and performs an authenticated VLESS+REALITY request
through every configured listener to an operator-owned HTTPS endpoint with an exact expected status.

**Dedicated probe identity** — `watchdog.reality_probe_client` names a unique
entry in `xray.clients`. Never reuse a recipient device credential.
Multi-cohort deployments authorize that identity in every cohort so a green
result covers every REALITY listener.

**P0 shape rendering is shared** — watchdog passes raw REALITY probe overrides
to `ansible/templates/p0-reality-shape.json.j2`, the same fail-closed renderer
consumed by Xray.

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

**Notification authority stays in systemd credentials** — the root-only JSON
input is loaded as `notifications.json`. The Python sender reads it internally;
the shell forwards only title, tags and body. An absolute request deadline and
the finite oneshot deadline prevent a notification stall from disabling probes.

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

- **Fresh-host check mode has no watchdog timer yet** — inspect the existing
  unit before rendering. Skip only its systemd operations when the unit is
  absent in check mode; normal convergence must still start it.
- **Direct script runs require loaded notification credentials** — use the
  service unit to exercise delivery. The environment file contains runtime
  settings only, and sender failures never log credential or destination values.
- **Owned Molecule containers need shared runtime propagation** — inspect `/run`
  as an existing mountpoint and prepare it as recursively shared before either
  watchdog scenario converges. Assert shared propagation afterward; a private
  runtime mount prevents the credential helper namespace from publishing its
  read-only credential filesystem to the main service. Production units and
  credential ownership/link/mode checks remain unchanged.
- **Failure fixtures must provision the real unit's sandbox paths** — the
  synthetic Xray service does not create `/var/log/xray`. Prepare that mandatory
  `ReadWritePaths` directory as root:xray 0750 before enabling the watchdog timer;
  an absent path can reject unit namespace setup before any probe or delivery.
  A failure-only sender wrapper reports loaded credential stat metadata in the
  main service child, then execs the actual sender with its original arguments,
  stdin and environment. Diagnostics never read credential contents and retain
  the required invocation and actual-notification failure.
- **The canary is part of the contract** — it must be operator-owned, have valid public TLS, and return `watchdog_secrets.reality_probe_expected_status` (default `204`). A normal public site root can use `200` without exposing a dedicated health endpoint. Canary failure correctly makes the
  protocol signal red.
- **On-node is not outside-in** — self-dialing the public listener validates
  protocol configuration but cannot detect transit filtering that affects other
  networks. Rotation still requires an independent external client-path quorum.
- **A partial listener outage is a failure** — primary, fallback, and every
  cohort listener are all probed; one red listener increments the common
  consecutive-failure counter.
- **Xray validation opens its configured logs** — the service sandbox must
  keep the Xray log directory writable or `xray run -test` reports a false
  configuration failure before validating the listener contract.
- **Nginx validation opens its error log** — `nginx -t` needs the Nginx log
  directory writable inside the strict watchdog sandbox even though it only
  validates configuration syntax.
- **Inventory must preserve both addresses** — `make inventory` emits
  `vpn_service_address` beside `ansible_host`. Local SSH overrides may replace
  only the latter.

- Listener diagnostics and loopback wedge checks use the same configured REALITY
  probe manifest, including cohorts that omit the base port.
- Recovery budgets are validated before actions and atomically replaced with
  synced private temporary files. A corrupt existing budget fails closed rather
  than resetting hourly recovery and notification limits.

- Ordinary site convergence always invokes lifecycle reconciliation. The
  `watchdog_role_enabled` input selects enable or owned runtime retirement before
  secret/package guards. Disable stops units and removes only declared authority;
  shared packages, immutable runtime receipts, historical logs and recovery data
  remain available for a later explicit recovery.
