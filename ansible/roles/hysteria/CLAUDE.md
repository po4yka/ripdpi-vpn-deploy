# role: hysteria — P2 UDP/QUIC

## Design decisions

Molecule upgrades the previous stable fixture to the selected 2.13.0 runtime and checks its actual version, accepted service and both immutable release receipts. Keep download labels and post-upgrade assertions aligned.

ECH-required profiles bind the exact 2.13.0 runtime, owned inner identity and explicit outer name to a public SHA256 generation. The root-only ech.key enters the complete guarded transaction and LoadCredential; disabling ECH contributes exact absence authority. Candidate namespaces relocate the credential and prove a real ECH handshake. Resource profiles select fixed receive windows and explicit BBR settings; unsupported engines refuse before export.
Changed Hysteria authority opens the whole-route recovery boundary even when normalizer/gateway configuration is unchanged. ECH-only rotations must therefore retain site compensation; unchanged convergence does not open or quiesce that boundary.

- Matching node-local masquerade origins use a typed private hosts file bound read-only into this service. It maps the owned Nginx hostname to the provider IPv4 address only while that local frontend is enabled. External owned origins retain ordinary NSS. The file participates in guarded comparison, quiescence, publication and accepted rollback; global `/etc/hosts` is untouched.

- Site staging defers frontend rescue to the protected site transaction, which restores matching ingress before accepted frontend recovery. Standalone role reconciliation keeps its own guarded rollback.

- The guarded generation is the sole frontend lifecycle owner, including TLS
  changes and credential rotation. It reloads systemd before startup and proves
  authenticated readiness; delayed direct restart handlers cannot invalidate
  the admitted PID snapshot after activation.

- Temporary candidate allocation, validation and cleanup run on every ordinary pass but report no accepted-runtime change. Persistent publication and predictive change flags retain their real results; idempotence must not skip validation or hide a changed accepted file.

- The foreground service explicitly uses `Type=exec`. Successful manager startup must complete process setup and execution before strict runtime UID admission; journal and authenticated probes still establish application readiness.

- Candidate validation runs private staged source before quiescence. Detect validator byte changes without publishing them; installed validators and semantic companions are snapshotted and published only after the whole-route transaction opens. A rejected helper update cannot invalidate the accepted rollback receipt.

**Accepted units pin immutable executables** — frontend units execute their verified release paths directly. Publishing installer CLI links cannot change the executable used by an accepted unit after a rejected candidate. Xray candidate validation also selects the planned immutable executable and bundled asset release; runtime-aware checks derive both authorities from the loaded unit.

**One guarded SOCKS outbound carries TCP and UDP** — recipient names and literals enter the private normalizer at `127.0.0.1:12081` with independent internal authority. The YAML validator refuses direct fallback, extra outbounds, ACL and resolver overrides. Frontend startup follows the owned shared generation; normalizer loss stops Hysteria until guarded recovery.

**Masquerade admission uses the shared contract** — controller preflight,
secret validation, emitters and installed YAML validation accept only the owned
HTTPS proxy origin. The exact same `scripts/transport_semantics.py` is installed
beside the server YAML validator; keep the companion source together with that
consumer. Unsupported modes and origin disagreement fail before host changes.

Origins have no path, query, fragment, credentials or explicit default port.
When the local direct frontend is enabled, the origin must include its effective
nondefault HTTPS port. Scoped hosts resolution changes only the hostname lookup;
it never drops the port or changes global NSS authority.


**Port hopping keeps one unprivileged socket** — the config always binds `hysteria_port`; firewall-owned NAT redirects `hysteria_port_range` onto it. Do not pass a port union to Hysteria or grant it `CAP_NET_ADMIN`.

**Config validation is role-specific** — Hysteria exposes no safe
validation-only server command. The shared validator rejects malformed or
duplicate-key YAML and validates the required nested types and values before
publish; service liveness remains the runtime proof.

**One port, one identity** — Hysteria2 listens on `hysteria_port` (default
UDP/443). The server renders a per-client userpass map from `hysteria.clients`;
sing-box carries each credential as `name:password` in its password field.

**Bandwidth is negotiated per connection** — `bandwidth-capped` emits client
upload from the server download rate and client download from the server upload
rate. Official sing-box accepts integer Mbps hints, rounded up; server negotiation
clamps the exact configured rates. BBR profiles omit these hints. This is not an
aggregate or security rate limit, and RIPDPI currently ignores the hints. Each
supported bundle endpoint retains its own Salamander metadata. Hopping is
supported by official sing-box; RIPDPI export refuses it until the client is qualified.

**Pinned binary** — Hysteria version and architecture checksums are pinned;
the role delegates verified candidate publication and `current`/public/previous
rollback links to `runtime-release`. Like Xray, the version must be an exact
stable `vMAJOR.MINOR.PATCH` tag; empty and pre-release pins refuse before
acquisition.

**Masquerade follows an owned site** — `hysteria.masquerade_url` is required in production secrets and must equal `public_site_canonical_url` exactly (asserted in `tasks/main.yml`). This keeps QUIC probes on the same public identity without coupling the UDP-only role to nginx state.

Complete config, unit, origin hosts, TLS and runtime selections enter the private consumer plan. Native candidate admission runs the actual binary, unchanged protocol/listener/auth/outbound configuration and relocated TLS paths in an owned disconnected namespace under the consumer sandbox. Its exact native client must authenticate and forward before cleanup is confirmed; the namespace never pulls the live normalizer dependency. The configured dedicated probe client is also required for live process adoption. Shape validation alone cannot commit a runtime.

## What's done well

- **Fresh-host check mode remains a plan** — the role requires a planned unit install when the Hysteria service does not yet exist, then leaves activation to the real converge.
- **TLS reuses the P1 certificate material** — saves a renewal path. The
  operator supplies the same PEM pair to `hysteria.cert_pem`/`key_pem` and
  `nginx_xhttp.cert_pem`/`key_pem`; each role writes its own copy (no shared
  mount).

The staged runtime-release include returns generic `runtime_release_candidates`; this consumer appends them to its transport transaction before adding complete TLS and configuration authority.

## Pitfalls

- **UDP/443 is heavily policed in RU** — some carriers QUIC-throttle on UDP/443
  but not UDP/8443. Have `--port` flexibility ready; don't assume 443.
- **UDP ceilings belong to baseline** — its bounded `rmem_max`/`wmem_max` inputs
  are optional performance settings. Observe effective values and receive drops;
  a rendered value alone does not prove that the kernel applied it.
- **systemd unit `LimitNOFILE` matters** — default 1024 caps concurrent
  flows. The unit template sets `LimitNOFILE=1048576`.
- **No JSON API surface** — Hysteria's optional traffic API would be a
  fingerprint vector if exposed; it's disabled.
- **Do not point masquerade at an unrelated public site** — keep `hysteria.masquerade_url` equal to `public_site_canonical_url`; the pre-flight assert rejects anything else.

- Ordinary site convergence always invokes lifecycle reconciliation. The
  `hysteria_role_enabled` input selects enable or owned runtime retirement before
  secret/package guards. Disable stops units and removes only declared authority;
  shared packages, immutable runtime receipts, historical logs and recovery data
  remain available for a later explicit recovery.
