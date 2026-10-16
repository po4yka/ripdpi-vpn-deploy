# Direct XHTTP delivery profiles

The primary endpoint retains its existing tag. Enabling
`nginx_xhttp.fallback_enabled` in the host profile also exports a separately
selectable `:alternate` endpoint using `nginx_xhttp_fallback_port`. Its TLS SNI
and HTTP host come from `fallback_server_name`, or the primary hostname when
omitted. A distinct hostname requires its own admitted certificate/key pair.
Nginx and provider/firewall listener ownership remain unchanged.

| Output | XHTTP modes | Tuning | Selection |
|---|---|---|---|
| Official sing-box | none | none | supported P0/P2 only |
| RIPDPI | auto, stream-up | none; unsupported tuning refuses | primary and enabled alternate nodes |
| Native Xray v26.3.27 | auto, packet-up, stream-up | bounded-pool | one loopback SOCKS listener per endpoint |

`make emit-xray CLIENT=<name>` uses the same selected-device materializer as
bundle emission. This isolated Make entry point accepts literal `HOSTS`,
`COHORTS`, `SOPS_FILE`/`SOPS_FILES` or explicit `SECRETS_FILE` inputs and does
not load `.fleet.mk`. It produces native P1-only JSON, with consecutive SOCKS ports
from 1080 in host order (primary, then its alternate). Inbound/outbound tags
identify each endpoint. Each inbound has one exact route; unmatched traffic
hits blackhole. It does not open a public client listener or change established
sessions. Existing subscription/bundle formats retain their explicit formats.
Treat native JSON as private credentials: capture only into a new owner-private
file in an owner-controlled directory, then run the exact engine's
`xray run -test -config <private-file>` before adopting it. Do not log it or pass
it as a command-line value. Local port conflicts must be resolved before startup.

Optional secret input (omit it to keep upstream defaults):

```yaml
xray:
  xhttp_mode: stream-up
  xhttp_tuning:
    profile: bounded-pool
    max_connections: 2
```

The admitted bound is integer connections 1–4, with mode `stream-up`.
Both fields are required, unknown fields refuse, and only v26.3.27 is qualified.
The native outbound receives `maxConnections` and fixed zero (unlimited reuse)
for `hMaxRequestTimes`, `hMaxReusableSecs` and `cMaxReuseTimes`.
Short request/age rotation was rejected in the actual runtime: retiring a pool
drops its manager reference without immediately closing its sockets (43 live
connections were observed for a nominal two-element pool). Positive retirement
limits therefore refuse rather than claiming a hard connection bound.
These are outbound pool controls; the server inbound receives the shared mode only. No arbitrary JSON, mode downgrade,
request-bound omission or RIPDPI importer loss is accepted. The optional profile
is disabled by omission and is not automatically promoted to production.
Changing server mode requires redistributing matching recipient profiles before
activation; use the accepted baseline and its original profiles for rollback.

`make test-xhttp-delivery-matrix` runs the complete endpoint suite in an owned
isolated Linux root lab. Real native processes exercise both configured TLS
ports, distinct SNI, wrong credentials/certificate, primary outage, guarded
destination rejection and rejected-candidate preservation. Each admitted mode
proves untuned transfer. For stream-up the matrix compares default pools to bounded pooling, transfers exactly 1 MiB in each direction,
waits through an idle interval, restarts the client process, applies the same
2 ms / 20 Mbit namespace-only constraint to both profiles, and restores baseline.
Acceptance requires exact echoed bytes, at least 0.02 MiB/s, median echo latency
at most 2 seconds, candidate throughput at least 10% of the corresponding baseline,
client RSS at most 256 MiB, and live frontend connections no greater than the
configured pool bound. The matrix exercises pool bounds 1, 2 and 4. This is a
bounded local regression bar, not a performance recommendation or a long-duration capacity claim.

Liveness probes every emitted variant independently. Join its `variants[].variant`
index to `public_profiles` for that protocol: the map records `endpoint`, `server`,
`port`, TLS identity, mode and optional tuning without device credentials. A
successful alternate can establish P1 availability, while the primary variant
remains failed; it never establishes primary health. No automatic fingerprint
rotation or session interruption is introduced.

Acceptance is local only: the existing evidence categories `staging` and `client`
refer to the disconnected local runtime harness and pinned native fixture process.
There is no external staging soak, physical/external client acceptance, production
rollout, DNS/certificate issuance or credential mutation. Stable production pins,
classical P0 and [PQE HOLD](PQ-REALITY-ADOPTION.md) remain unchanged.
