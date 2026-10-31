# Client-side known issues and version pins

> **Status:** Current · **Type:** reference · **Tier:** CORE · **Reviewed:** 2026-10-21

The server stack is only one half of the story. These items are
client-side, but the operator distributing clients should know about
them because a vulnerable client undoes the server's protections.

## PQ-REALITY is on HOLD

The canonical capability is VLESS Encryption (PQE) over REALITY. It is distinct from the browser-facing `X25519MLKEM768` key share in uTLS. The current `make emit-singbox`, `make emit-bundle`, and VLESS URI paths remain classical: they do not emit Xray's VLESS Encryption setting and must not advertise PQE compatibility.

Do not pair these artifacts with a PQE-enabled server inbound. Server-only enablement would make the supported client output incompatible. `docs/decisions/0006-pq-reality-adoption.md` defines the machine-enforced HOLD phase and the evidence required before a future server/client implementation can enter STAGING.

## Strict dual-stack kill-switch bundles

`make emit-singbox` now emits the supported unified IPv4/IPv6 TUN
`address` list and removes the default cleartext local-DNS and
private-network routes. It also uses typed DNS servers and route-level
`sniff`/`hijack-dns` actions required by sing-box 1.13. The standard artifact
contains P0 REALITY and P2 Hysteria2 only. P1 XHTTP is available through
`emit-bundle` and the explicit `emit-xray` native format because official sing-box
does not implement that transport. See [XHTTP delivery profiles](xhttp-delivery-profiles.md).
Regenerate and redistribute existing profiles after upgrading.
`--per-app-bypass` still emits an intentional non-lockdown profile, but
`make check-killswitch BUNDLE=…` rejects that profile by design.

The checker certifies one full-device TUN only. It refuses address, interface,
user, package and MAC inclusion or exclusion policies, including route rule sets.
MPTCP bypass and capture inside a separate network namespace also fail.
An empty selection list retains the default capture policy. A partial TUN
profile can be intentional, but it cannot pass this full-device check.
Malformed profile structures and non-boolean route flags also fail.

## SOCKS destination identity and stream lifecycle

The server normalizer accepts lossless Unicode DNS names such as
`bücher.example` and explicit ASCII A-labels such as `xn--fa-hia.de`.
Its dependency-free name policy refuses Unicode that the available IDNA codec
maps to another identity, including sharp-s, final sigma and joiners. Supply
the intended ASCII A-label for those names. The policy never maps `faß.de`
silently to `fass.de`.

The cascade adapter forwards each TCP FIN only after pending data drains.
The opposite direction can send a response after that FIN. Bounded buffers and
the idle deadline apply in both directions. The authenticated UDP normalizer
forwards empty datagrams as data, with the same destination, source binding,
size limits and association quarantine as non-empty datagrams.

## AmneziaWG Android split-tunnel localhost leak (issue #2457)

Status: **open, unresolved** as of 2026-05-09. Source:
the local client release notes.

Apps placed on AmneziaWG 2.0 Android's per-app split-tunnel exclusion
list can still reach `127.0.0.1` and probe the VPN tunnel interface
from there. A detection-capable app (banking app, marketplace, etc.)
that is excluded from the VPN to satisfy an IP-origin check can still
fingerprint that an AWG tunnel is active on the device.

Mitigations until upstream lands a fix:
- Use Android Work Profile (Shelter) — full sandbox separation makes
  the loopback probe path inaccessible.
- Use router-level VPN instead of per-device — no local tunnel
  interface on the phone.
- Do not rely on per-app exclusion to satisfy an IP-origin check on
  Android 2.0 AmneziaWG clients.

The desktop and iOS AmneziaWG clients are not affected.

## NaiveProxy padding leak in sing-box <=1.13.7

Status: **fixed**. Pin clients at sing-box >= 1.13.8 (2026-04-14) or
NaiveProxy-via-cronet-go with the analogous fix.

Older sing-box NaiveProxy implementations allocated padding buffers
from a shared pool without zeroing on reuse, leaking domain names and
request fragments from previous tunnel users into another user's
padding. The privacy and detection consequences are both serious —
patterned padding distinguishes sing-box NaiveProxy from genuine
Chromium traffic, and on a multi-tenant relay the leak crosses user
boundaries. Refs: sing-box PR #4001, issue #4002, cronet-go PR #7.

When emitting client configs via `make emit-singbox`, ensure the
target client binary is recent enough. The server bundle does not
ship clients, but the QUICKSTART and SUBSCRIPTION-PLANE docs should
point operators at the minimum versions.

## NaiveProxy v147 preamble injection (use >= v147 for preamble cover)

NaiveProxy v147.0.7727.49-3 (released 2026-05) and the follow-on
v148.0.7778.96-2 (2026-05-02) inject realistic Chrome HTTP/2 preambles
derived from the fronting Caddy site's root page. The server-side
`naive` role's native Caddy JSON configuration enables zstd and gzip compression
for the fronting site. Use suitable root-page content for the selected cover.

The feature is on by default in v147+. Clients without this feature lack
the preamble cover. The preamble change alone does not establish either
compatibility or incompatibility with the pinned Caddy/forwardproxy build.
Qualify the exact client and server build in staging with authenticated
traffic before distribution; retain TLS verification and the previous
working client/server pair for rollback.

Use the current reviewed client release to track Chromium signatures. The server
disables access logging and excludes `http.log.access` and `http.log.error`
because failed CONNECT requests can contain activity metadata. An ERROR-only
access logger also contains request metadata for 5xx responses. The role pins
Caddy 2.11.7 and the reviewed forwardproxy commit. Native acceptance covers
authenticated traffic, failed CONNECT and stream reset.

## VLESS desktop client VPS-IP exposure (2026)

Refs: local client release notes.

The VPS exit IP is observable from a desktop client process by an
attacker with code-execution rights on the device (telemetry SDKs,
ad libraries, certain installer wrappers). This is a client-side
defect; nothing the server can do about it. Audit the client binary's
network behaviour before distributing to a high-risk cohort.

## VLESS Android SOCKS5 client exposure

Refs: `docs/reference/client-notes.md` and the client release notes.

Some VLESS Android clients expose a local SOCKS5 listener that
non-VPN apps on the same device can reach. This is functional design
for per-app routing, but it lets a detection-capable app determine
that a proxy is running by probing the local port. Per-app routing
should be configured via packageNameRegex rather
than via app-side SOCKS5.

## VLESS+REALITY alt-port roll-over (xray_fallback_port)

The secondary VLESS+REALITY+Vision inbound is disabled by default:
`xray_fallback_port: 0`. An operator may select a nonzero alternate port after
measuring a path-specific benefit. A port number alone does not make the
listener indistinguishable from HTTPS or overcome IP-level blocking.

An enabled alternate distinct from `xray_port` adds a second recipient outbound
sharing the same REALITY identity. Ordinary sing-box selection retains its
latency-only urltest behavior; it does not verify useful response bytes. An
explicit RIPDPI payload-failover policy uses its coordinated consumer instead.

Enabling an alternate requires the same port in the explicit Terraform
`public_listeners` contract and the Ansible runtime input. Provider/runtime
preflight continues to reject a mismatch. The firewall role derives its rules
from that admitted contract; no manual nftables edits are needed. Multi-cohort
layouts declare each listener explicitly and bypass the default alternate.

Existing private configurations are not rewritten by this source change. Keep
both runtime and provider declarations explicit when retaining an alternate;
removing a live listener requires an authorized coordinated rollout and refreshed
recipient profiles.

## REALITY client clock window

Every REALITY inbound sets `maxTimeDiff` from `xray_reality_max_time_diff_ms`,
which defaults to 90000 ms. Without it, Xray accepts a captured ClientHello at
any later time. A replayed hello then takes the authenticated REALITY path
instead of the borrowed target's handshake, and that difference can identify the
node. A device whose clock is more than 90 s off fails P0 silently: it receives
the target's certificate and no tunnel. Fix the device clock (automatic network
time); do not widen the window to compensate. The role refuses zero, which
disables the check.

## uTLS fingerprint + the "TLS frozen" failover caveat (domestic-AS cascade only)

The client uTLS fingerprint for the REALITY and XHTTP outbounds is configurable
per profile via `xray_utls_fingerprint` (xray role default `chrome`; override in
group_vars, or `UTLS_FINGERPRINT=firefox make emit-singbox CLIENT=name` for a
single run). Hysteria2's QUIC TLS has no uTLS knob, so this does not apply to it.
The watchdog and smoke-test REALITY clients, and the watchdog XHTTP client, send
the same configured value, so they verify the fingerprint that recipients use.

**Honest scope — not active on the baseline.** This matters only under the
June-2026 three-condition TLS pattern, whose Condition 1 requires the
*server* to sit on a flagged domestic cloud AS. The baseline runs foreign VPS (UpCloud / Hetzner / Vultr), which take
a different enforcement path (TCP port-range, not this TLS-rate rule). So this is
a **latent** caveat for any domestically hosted relay/cascade node and general client
guidance — **not** an active baseline threat. Do not over-state it elsewhere.

Under that domestic-AS pattern:

- **Fingerprint class (Condition 2)** flags Chrome/Safari/iOS; Firefox and
  standard Android currently pass. For a domestically hosted cohort, pre-selecting
  `xray_utls_fingerprint: firefox` sidesteps Condition 2 — but pick once and
  hold it (see the caveat below).
- **Failover-backoff caveat.** When the observed failure shape is **"TCP
  reachable but TLS frozen"** (TCP handshakes still connect, TLS stalls), the
  client should **back off and wait out the freeze** rather than thrashing
  through transports/fingerprints. The first violation is a ~120 s TLS freeze;
  **rotating the uTLS fingerprint while that freeze is active escalates it to a
  600 s full block.** An automated fingerprint-rotation loop is therefore
  counterproductive here. (Rolling over to a structurally different transport or
  port is not itself the trigger — it is *fingerprint* churn during the freeze
  that escalates. The emitted bundle never rotates the uTLS fingerprint, and
  `interrupt_exist_connections` is `false`, so the default config does not trip
  this on its own.)
- **HTTP/2 structural advantage (XHTTP).** The XHTTP path multiplexes concurrent
  requests into a single TLS session, keeping the per-SNI TLS connection count
  below Condition 3's burst trigger (>3 parallel TLS to the same SNI within
  ~350–400 ms).

## sing-box clients: use the standard artifact

When `make emit-singbox CLIENT=name` is available, prefer the sing-box
JSON output over manual VLESS URI strings. It wires every supported P0/P2
transport into a single selector + urltest group, which matters for the
home-ISP TLS policing failure mode. The standard artifact's urltest interval
is 30 minutes: a shorter cadence opens one session per transport to the same
address in a synchronous burst, which is the concurrent-session pattern that
policing targets. The RIPDPI bundle keeps the cadence recorded in the vendored
contract fixtures until the paired client change lands. P1 XHTTP requires an Xray-family profile
or the RIPDPI-specific bundle; never copy that unsupported outbound into the
standard document.

## Hysteria ECH-required profiles

The supported pair is Hysteria 2.13.0 and official sing-box 1.14.3. An explicit
`hysteria.ech` object binds `profile: ech-required`, `inner_name`, `public_name`,
`config_list`, `keys_pem` and `generation` (SHA256 of the decoded public list).
The inner name equals the owned masquerade/certificate identity. The distinct
outer name is the visible SNI; choose an operator-owned DNS name. Public ECH
configuration is distributed inline, with no DNS discovery or automatic fallback.
Salamander and ECH cannot be selected together in this technical profile.

Use the reviewed exact Hysteria executable for generation. The following command
mutates only the named encrypted source; it does not deploy or redistribute it:

```bash
SOPS_FILE=/private/config/staging.secrets.sops.yaml \
HYSTERIA_BINARY=/private/tools/hysteria \
HYSTERIA_ECH_PUBLIC_NAME=outer.example.com \
HYSTERIA_ECH_INNER_NAME=vpn.example.com \
make issue-hysteria-ech
```

Issuance verifies the executable checksum, generates within an owned private
directory, validates private/public key agreement and publishes through the
existing locked SOPS transaction. Only the generation identity reaches stdout.
Fresh bootstrap also accepts `--ech-public-name` with the same verified binary.

The role stages the complete root-only key, config, unit and TLS generation.
`LoadCredential` gives the unprivileged service its private key. Native admission
relocates that credential into its owned candidate unit before authentication;
activation failure restores the previous complete authority. Removing `ech`
selects classical TLS and retires only the managed ECH key.

Rotation replaces the entire ECH generation without an overlap window. Prepare
new recipient artifacts privately, activate the new server generation and then
distribute the matching public profile. Existing clients with only the old list
fail after activation; no plaintext retry is allowed. A failed activation retains
the old generation. A successful rotation therefore needs a coordinated recipient
cutover or a separately named endpoint. Keep prior encrypted source authority for
an explicitly requested rollback after a committed cutover.

RIPDPI bundles are outside this ECH support set and refuse export before producing
an artifact. Classical profiles remain supported separately. Liveness keeps the
exact ECH public list and refuses stripped or mismatched generations. For paired
XHTTP monitoring, `--profile-format ripdpi --xhttp-only` explicitly emits only
the XHTTP intermediate consumed by Xray; it never emits an ECH Hysteria profile.

Resource profiles are `bandwidth-capped`, `bbr-conservative` and `bbr-standard`.
The first profile emits official sing-box `up_mbps` from the server download rate
and `down_mbps` from the server upload rate. Positive rates round up to integer
Mbps; server negotiation clamps them to the exact configured rates. These hints
select Brutal and apply per connection. They are not an aggregate server limit
or a security bandwidth ceiling. Set rates that the client path can sustain.
Every device of a node receives the same pair on purpose: the values travel
inside the encrypted QUIC stream, so they are not an on-path fingerprint, the
server clamps them to its configured rates anyway, and liveness refuses a
profile whose pair differs from the node's configuration
(`wrong-hysteria-bandwidth`). Vary rates per node, not per device.
The RIPDPI importer does not apply these bandwidth hints. Do not rely on this
profile to limit that client's rate. Hopping is supported for official sing-box
and the qualified native RIPDPI client. RIPDPI export retains the configured
range and fixed interval in standard fields and matching extras. Intervals use
whole seconds, minutes or hours and must be at least 5 seconds and at most
9223372036854 milliseconds. Older clients do not satisfy this contract.
BBR profiles omit bandwidth hints and set both runtime congestion and recipient
BBR policy; the server ignores advertised client bandwidth for its BBR selection.
Kernel UDP ceilings belong to baseline,
are bounded between 1 MiB and 64 MiB, and default to 7,500,000 bytes. TCP BBR is
independent of QUIC behavior. Measurements must establish any performance claim.
BBR recipient profiles are qualified for official sing-box only; RIPDPI export
refuses them. Bandwidth inputs must be positive integer rates of at most 1 Gbps;
previous values above that ceiling now refuse before mutation.

Before promotion, refresh stable channel, asset and advisory metadata with
`python3 scripts/hysteria_release.py`. Unknown metadata blocks publication-age
eligibility. Passing this check proves neither the required 48-hour staging soak
nor authorization to deploy. Run `make test-hysteria-ech-runtime` and
`make test-hysteria-resource-profiles` in the isolated Linux root environment;
packet capture, actual recipient traffic and full transaction compensation remain
required. Production promotion follows a separately authorized bounded 48-hour
staging soak, reconnect checks and exact-generation rollback rehearsal.

## Direct XHTTP endpoint and tuning selection

The RIPDPI-format producer emits a primary XHTTP outbound and an independently
selectable `:alternate` outbound when the selected profile enables the alternate
listener. Each uses its own effective port and TLS name. Mode passes unchanged into the exact Xray adapter. Native Xray and monitoring
output support the qualified `stream-up` bounded-pool profile on `v26.3.27`;
RIPDPI export refuses fields its importer cannot consume. See
[XHTTP delivery profiles](xhttp-delivery-profiles.md) for fields and limits.

The local acceptance matrix exercises actual Xray processes, transfer, faults
and rollback. External recipient adoption and device testing are outside the
owner's local completion scope. Official sing-box output remains free of
unsupported XHTTP fields. A working alternate preserves connectivity, while a
failed or indeterminate primary keeps the aggregate liveness decision degraded;
it does not by itself request node rotation.
