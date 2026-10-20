# role: watchdog — self-healing service supervision

## Design decisions

Native REALITY probes use the same typed Sudoku TCP mask as the server when
the opt-in shape requests it. Finalmask belongs to `streamSettings`, not
`sockopt`. These clients use Xray Mux.Cool for the mux shape; sing-mux recipient
delivery remains unsupported.

Probe-port vacancy is checked before starting the owned REALITY client; occupied ports cause a red observation without authorizing runtime recovery. Startup uses a monotonic deadline. Ready sockets must belong to the retained client PID before and after the canary; local client loss or replacement cannot authorize server recovery. Authenticated round-trip failure alone has no restart authority; only failed host diagnostics select a service. Subscription-only profiles omit transport checks and Xray sandbox paths.

P1 diagnostics check the effective primary and enabled alternate nginx frontend ports and Xray backend independently, including P1-only profiles. Backend failures enter guarded Xray recovery and never restart healthy nginx. Diagnostic listeners remain distinct from authenticated native acceptance.

XHTTP frontend sockets belong to nginx and the localhost backend belongs to Xray. Dedicated authenticated XHTTP inbounds route every enabled primary/fallback endpoint through the canonical Xray TLS client, retaining the effective mode and bounded-pool controls. Backend diagnostics recover only Xray, including XHTTP-only hosts. A failed client round trip alone has no service-restart authority: credential, trust and canary failures remain red without restarting a healthy server.

Omitted XHTTP/Hysteria toggles retain the canonical enabled defaults in probe selection, private credentials and service deadlines. Explicitly disabled XHTTP has zero diagnostic ports and needs no XHTTP configuration, including standalone REALITY-only role convergence.

Hysteria uses a separately enrolled `hysteria.clients` watchdog identity, a private systemd credential, effective SNI/CA and matching Salamander. The ordinary environment contains only ports and paths. Each probe invocation holds a kernel lock inherited by its client. Process death releases the lock; a surviving client retains exclusion, and exact SOCKS PID ownership prevents a foreign listener from satisfying delivery. The service deadline budgets both Xray endpoint families and Hysteria startup/request time.

AWG probes use every normalized configured instance. The environment carries only comma-separated interface names; each failed interface maps to its exact `awg-quick@` unit. Subscription-only hosts emit no AWG probe list.

- Server configuration validation derives the accepted executable and asset paths from the loaded Xray unit. The operator CLI link remains available for stats and the separately pinned canary client, but never chooses the accepted server validator.

- The watchdog failure scenario declares a versioned synthetic runtime and a
  canonical guarded server configuration. Its CLI symlink does not select the
  accepted validator. The scenario proves notification delivery for an
  intentionally protocol-red listener; it does not establish native Xray parser
  or authenticated transport completion.

Budget files are owner-only 0600. Under the parent directory inode lock, a
known owned single-link 0640 budget migrates only after complete typed payload
validation, preserving bytes/counters and fsyncing file and directory. Unsafe
ancestry, foreign files and malformed budgets refuse without repair or reset.
Descriptor cleanup includes stream-wrapping and temporary-unlink failures.
Entropy is obtained before opening files. Each acquired descriptor belongs to
an explicit lexical try/finally context, including ancestor traversal failures.
The directory walker transfers ownership before closing an old parent; read
absence is recognized only at initial acquisition, never after a body failure.

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
requests targeted Xray/Hysteria recovery from the guarded generation controller; other failed units retain their direct recovery. A failed configuration check (`xray config valid`, `nginx -t`) stays red and alerts, but withholds recovery for that unit in the same run: a restart would stop a service that still holds its last valid configuration. A false validation failure (for example an unwritable sandbox log path) therefore also blocks recovery until it is fixed; the red result and alert remain. Only the controller may replace a protected frontend and acknowledge its new admitted PID while retaining healthy frontend and mapping processes. A failed controller request has no direct-restart fallback. Restart attempts remain
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

- The finite watchdog service deadline reserves three controller control budgets plus completion margin for each enabled protected frontend, in addition to existing probe and other recovery budgets. The supported 60-second controller setting cannot truncate a second protected request before state publication.
