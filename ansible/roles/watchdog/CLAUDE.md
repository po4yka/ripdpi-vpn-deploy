# role: watchdog — self-healing service supervision

## Design decisions

**Two-level supervision** — systemd is layer 1 (Restart=on-failure). The
watchdog role adds layer 2: a timer that records unit, listener, and
configuration diagnostics and performs an authenticated VLESS+REALITY request
through every configured listener to an operator-owned HTTPS 204 canary.

**Dedicated probe identity** — `watchdog.reality_probe_client` names a unique
entry in `xray.clients`. Never reuse a recipient device credential.
Multi-cohort deployments authorize that identity in every cohort so a green
result covers every REALITY listener.

**Bounded alerts** — failures must cross `fail_threshold`, and notifications
remain capped by `alerts_per_hour_max`. The watchdog reports failures; systemd
owns service restart policy.

## What's done well

- **Protocol completion is load-bearing** — a `204` returned through the temporary
  SOCKS client proves the configured UUID, short ID, REALITY key/SNI, listener,
  and outbound request path completed.
- **Probe secrets stay root-only** — the generated Xray client config is `0600`;
  credentials never enter the environment file, command line, journal, or alert
  body.
- **Cleanup is unconditional** — the temporary Xray client is terminated after
  success, failure, startup timeout, or signal.

## Pitfalls

- **The canary is part of the contract** — it must be operator-owned, have valid
  public TLS, and return exactly `204`. Canary failure correctly makes the
  protocol signal red.
- **On-node is not outside-in** — self-dialing the public listener validates
  protocol configuration but cannot detect transit filtering that affects other
  networks. Rotation still requires an independent external client-path quorum.
- **A partial listener outage is a failure** — primary, fallback, and every
  cohort listener are all probed; one red listener increments the common
  consecutive-failure counter.
