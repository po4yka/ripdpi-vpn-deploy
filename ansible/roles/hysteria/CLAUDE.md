# role: hysteria — P2 UDP/QUIC

## Design decisions

**One port, one identity** — Hysteria2 listens on `hysteria_port` (default
UDP/443). The server renders a per-client userpass map from `hysteria.clients`;
sing-box carries each credential as `name:password` in its password field.

**Bandwidth limits per protocol, not per client** — server-side cap is set
once in `config.yaml`; per-client tuning is in the client config emitted by
`scripts/emit-singbox.sh`. Don't try to per-client throttle on the server.

**Pinned binary** — Hysteria version and architecture checksums are pinned;
the role delegates verified candidate publication and `current`/public/previous
rollback links to `runtime-release`.

**Masquerade follows an owned site** — `hysteria.masquerade_url` is required in production secrets and must be an HTTPS origin controlled by the operator. This keeps QUIC probes on the same public identity without coupling the UDP-only role to nginx state.

## What's done well

- **TLS uses the same cert as P1** — saves a renewal path. The `nginx-xhttp`
  role's cert directory is read-only-mounted into the Hysteria service.
- **Brutal-style congestion control is off by default** — toggled via
  `vpn.hysteria_brutal`. Brutal aggressive ramp can attract DPI heuristics
  on some carriers.

## Pitfalls

- **UDP/443 is heavily policed in RU** — some carriers QUIC-throttle on UDP/443
  but not UDP/8443. Have `--port` flexibility ready; don't assume 443.
- **Hysteria does not survive a kernel UDP buffer too small** — the role sets
  `net.core.rmem_max` and `net.core.wmem_max` (baseline does the same; we
  re-assert to be sure).
- **systemd unit `LimitNOFILE` matters** — default 1024 caps concurrent
  flows. Set to `65536` in the unit file template.
- **No JSON API surface** — Hysteria's optional traffic API would be a
  fingerprint vector if exposed; it's disabled.
- **Do not point masquerade at an unrelated public site** — override `hysteria.masquerade_url` only with another operator-owned HTTPS origin.
