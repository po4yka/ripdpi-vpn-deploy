# role: xray — P0 VLESS+REALITY+Vision

## Design decisions

P0 recipient delivery refuses the mux shape. Xray Mux.Cool and sing-mux are
different wire protocols; an empty VLESS flow does not make them compatible.
Native Xray smoke and watchdog clients retain Mux.Cool. The opt-in Sudoku
shape uses typed `streamSettings.finalmask.tcp` with the pinned default settings
on both ends. It changes traffic appearance only; VLESS and REALITY still own
authentication. Never put Finalmask under `sockopt`, where Xray ignores it.

XHTTP server mode shares admission with recipient emission. Optional typed
bounded-pool tuning is qualified for v26.3.27 native Xray outbounds only; XMUX
pool controls belong to the client and are never copied into the server inbound.
No production pin, default mode, P0 shape or PQE eligibility changes with it.

- Site staging defers frontend rescue to the protected site transaction, which restores matching ingress before accepted frontend recovery. Standalone role reconciliation keeps its own guarded rollback.

- The guarded generation is the sole frontend lifecycle owner. Candidate
  validation and whole-route snapshot/quiescence precede changed publication;
  activation reloads systemd and requires authenticated readiness. No delayed
  frontend restart handler may change an admitted PID after that boundary.

- Temporary candidate allocation, validation and cleanup run on every ordinary pass but report no accepted-runtime change. Persistent publication and predictive change flags retain their real results; idempotence must not skip validation or hide a changed accepted file.

- The foreground service explicitly uses `Type=exec`. Successful manager startup must complete process setup and execution before strict runtime UID admission; journal and authenticated probes still establish application readiness.

- Recipient address isolation belongs to the canonical normalizer and final packet guard. Do not add a GeoIP-only private rule to the AsIs frontend: asset ranges can reject literals while names resolve to the same admitted address downstream.

- Protected Xray service identity is fixed at `xray:xray`, matching actual shared frontend UID admission. Alternate runtime user/group settings fail before host mutation; the controller cannot report a different probe identity as frontend readiness.

- Candidate validation runs private staged source before quiescence. Detect validator byte changes without publishing them; installed validators and semantic companions are snapshotted and published only after the whole-route transaction opens. A rejected helper update cannot invalidate the accepted rollback receipt.

- Frontend-only credential, unit, validator and selected geodata changes open
  the canonical whole-route transaction even when gateway inputs are unchanged.
  Compare staged geodata against active assets; a cached candidate is not proof
  that the served pair is unchanged. Revocation rescue retains this outer owner
  and quiesces the consumer without restoring removed credentials.

**Accepted units pin immutable executables** — frontend units execute their verified release paths directly. Publishing installer CLI links cannot change the executable used by an accepted unit after a rejected candidate. Xray candidate validation also selects the planned immutable executable and bundled asset release; runtime-aware checks derive both authorities from the loaded unit.

**Recipient egress is authenticated and guarded** — the direct and optional WARP outbounds target fixed local normalizer listeners; no Freedom or DNS recipient outbound remains. Requested DNS destinations and non-A payloads retain their authority. Runtime-aware validation rejects an unguarded rollback topology before native parsing. Loss of the normalizer stops the frontend; the owned generation controller resets gateway mappings and recovers enabled frontends.

**Explicit cohorts require admitted membership** — the shared transport
preflight runs before helper installation or runtime publication. Every cohort
has a unique name and explicit nonempty, unique references to known clients.
Schema, emission and liveness consume the same semantic rules; invalid inputs
never rely on later native parser failure to protect the existing service.


New log inodes start private at 0600. Only after both no-follow single-link
entries validate does provisioning grant the explicit Xray group read access.
The capability-bounded policy reader joins that group without DAC bypass.
Descriptor contexts own all acquired files and ancestors through failures.
Each raw acquisition closes in its own lexical finally; log provisioning uses
metadata descriptors directly without allocating unnecessary text buffers.
The fixed pair uses nested lexical contexts; directory traversal owns only its
current descriptor and transfers that ownership before closing an old parent.

**Configuration validation shares one executable contract** — `files/xray_validate.py` is installed as `/usr/local/libexec/vpn-xray-validate`. Read-only verify always streams that same repository source into remote Python, so checking an existing node never requires installing or updating the helper first. Candidate convergence supplies the planned asset directory explicitly; verify, rotation, rollback and watchdog derive the exact asset directory from the loaded Xray unit. Missing or ambiguous authority fails closed without printing environment values.

**Drift is a read-only role entry point** — `tasks/drift.yml` compares the inventory-and-secrets render with the complete normalized deployed configuration under `no_log`; diagnostics never print config values.

**Single source of REALITY config** — `templates/config.json.j2` is the
SOT for the Reality inbound. Other roles (firewall, nginx-xhttp) read ports
from `defaults/main.yml`; they never copy the inbound config.

**P0 shape rendering is shared** — `ansible/templates/p0-reality-shape.json.j2`
is the sole renderer for the accepted Vision and mux shape declarations in
`group_vars/all.yml`. Xray and watchdog pass raw overrides to that template;
unknown modes fail before render.

**Pinned binary** — the Xray version is the SOPS secret `xray.version`;
`defaults/main.yml` holds only an empty sentinel that the role asserts is
overridden. Upgrades go through `docs/reference/xray-release-line.md`. The release-line tracker exists
because v26.2.6 → v26.5.3 had silent flow-mode breakage on some clients.
Binary acquisition is delegated to `xray-runtime`; this role owns only the
primary service user, configuration, logs, and lifecycle.

**Explicit asset lookup** — template validation, restart validation, and the
systemd service use the same `XRAY_LOCATION_ASSET` directory. The geodata role
populates it when enabled; otherwise `xray-runtime` publishes the
archive-bundled GeoIP file below the Xray install root. The two modes keep
disjoint path ownership so an enable/disable transition cannot replace one
role's regular file with the other role's symlink.

**XHTTP can run without REALITY** — the role runs when either transport is enabled. The XHTTP inbound binds only to `127.0.0.1`; when `vpn.enable_xray_reality` is false, no public REALITY inbound or REALITY target validation is emitted.

`trustedXForwardedFor` contains the `X-Forwarded-For` header name, not a proxy
address. Every shared frontend overwrites that header with its admitted peer;
never append a supplied chain. The input path shares controller admission with
Nginx and liveness emission, so unsupported endpoint syntax fails before staging.

**StatsService is local-only** — traffic and online-user counters are enabled
for redacted diagnostics, but the gRPC API binds only to
`xray_api_listen=127.0.0.1:10086`. The monitoring role owns export and
retention; this role owns only the Xray-side counter contract.

**Log directory entries belong to root** — convergence opens every path
component without following links, claims the log directory as root:xray 0750,
and validates regular single-link logs before descriptor-backed metadata writes.
Xray owns only the 0640 log files; startup has no privileged pathname repair.
Rotation creates fresh runtime-writable files and restarts the active service.
The command appends `--check` only in check mode; normal convergence sends no
placeholder argument. JSON change reporting is evaluated only after a successful
helper exit, preserving the helper's original failure result.

The default log root is `/var/lib/vpn-xray-logs`, separate from the runtime user's
home and the OS-managed `/var/log`. Ubuntu can grant group write on `/var/log`;
neither that shared ancestor nor the Xray-owned home meets this root-only path
contract. Keep the descriptor checks and the OS directory permissions unchanged.

Complete frontend authority is staged in the private `transport_runtime_candidates` plan. Native admission selects the staged asset directory; the unit retains the intended served asset directory, which is published with runtime links and config by consumer acceptance. Dedicated probe credentials must belong to the configured acceptance client in every enabled inbound/cohort. The owned canary supplies positive protocol traffic before the accepted receipt advances.

## What's done well

- **Idempotent inbound rebuild** — changed config or unit authority opens the
  guarded transaction; unchanged passes retain the accepted generation.
- **Multi-cohort support** — `vpn.xray_cohorts` is a list; each cohort gets
  its own inbound with its own `serverNames`, `shortIds`, flow_mode, and
  finalmask. See `docs/how-to/multi-cohort.md`.
- **Alternate inbound is opt-in** — `xray_fallback_port` defaults to 0.
  A nonzero port synthesises a second VLESS+REALITY+Vision inbound sharing
  the same identity and requires a matching explicit provider listener.
  Multi-cohort layouts use their declared ports instead. A second port is
  another candidate path, not proof of resilience to IP or payload blocking.
- **Backup-before-write** — the previous config is copied to `.prev` so
  `rollback-config.yml` has a target.
- **No client identifiers in exported metrics** — per-user counters are
  disabled in the Xray policy (only inbound/outbound aggregates are on), so
  client emails never reach the StatsService the monitoring exporter reads.
- **Fresh-host check mode** — the unit template must report a planned change
  when the unit is absent. Service activation waits for a real converge; an
  existing unit can still be checked without changing its state.

## Pitfalls

- **Reality `dest` is single-target per inbound** — you cannot have a single
  inbound fall back to multiple targets. Multi-cohort needs multiple inbounds.
  Don't try to express this in `settings.fallbacks` — those only apply *after*
  Reality has authenticated the client.
- **Short ID length must be even hex** — odd-length values silently break
  some clients (sing-box ≤ 1.10). The role's Molecule `verify.yml` asserts it.
- **Flow `xtls-rprx-vision` and XHTTP are mutually exclusive** — the XHTTP
  inbound's client entries omit `flow` entirely; only the REALITY inbound
  sets it. Don't add `flow` to the XHTTP client object.
- **`serverNames` first entry is special** — uTLS clients send the first
  entry as SNI. Rotating its order *is* a config change even though the set
  is identical.
- **Binary-pin drift on apt-update** — never `apt upgrade xray` blindly;
  the binary is hash-pinned via the release-line tracker.
- **10085 belongs to XHTTP** — keep StatsService on 10086 or another validated
  loopback port; the pre-flight guard rejects public binds and collisions.

- Ordinary site convergence always invokes lifecycle reconciliation. The
  `xray_role_enabled` input selects enable or owned runtime retirement before
  secret/package guards. Disable stops units and removes only declared authority;
  shared packages, immutable runtime receipts, historical logs and recovery data
  remain available for a later explicit recovery.
