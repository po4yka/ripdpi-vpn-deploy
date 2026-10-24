# RIPDPI Bundle — server-side schema specification

> **Status:** Current · **Type:** reference · **Tier:** — · **Reviewed:** 2026-10-21

> **The executable contract is [`contract/ripdpi-bundle.schema.json`](../../contract/ripdpi-bundle.schema.json)** — a JSON Schema (draft 2020-12) that is the single source of truth for the `ripdpi` object. This document is its prose companion. The schema is vendored byte-identical into the RIPDPI Android client repo and validated by a contract test in **both** CIs (`scripts/validate-bundle.py` + `tests/unit/test_bundle_schema.py` here; `RipdpiBundleContractTest` there), so the contract cannot drift silently between the two repos. When you change the shape of the `ripdpi` object, change the schema first.

## Overview

`emit-bundle.sh` (and `make emit-bundle CLIENT=<name>`) produces a single JSON
file that is the canonical subscription artifact for the RIPDPI Android client.
It uses the explicit RIPDPI profile format from `emit-singbox.sh`, extended
with a top-level `ripdpi` object carrying device-VPN and transport-obfuscation
metadata. Unlike the standard emitter output, this format includes P1 XHTTP,
which the RIPDPI client implements but official sing-box does not.

Do not send this artifact to standard sing-box clients. They may reject the
unknown top-level `ripdpi` field, and official sing-box rejects the XHTTP
transport. Operators serving those clients must use the `/sub` plain endpoint.

## Top-level structure

```jsonc
{
  // --- RIPDPI profile format from emit-singbox.sh ---
  "log":       { ... },
  "dns":       { ... },
  "inbounds":  [ ... ],
  "outbounds": [ ... ],   // includes P0/P1/P2 + selector/urltest
  "route":     { ... },

  // --- RIPDPI extension ---
  "ripdpi": {
    "schema_version": 1,
    "amneziawg":      [ <AWGEntry>, ... ],
    "hysteria_extras": { "<tag>": <HysteriaExtras>, ... },
    "topology":       <Topology>,        // declares split-hop / realm relay
    "expires":        "2026-12-31T23:59:59Z"  // optional; ISO-8601 UTC
  }
}
```

The validator also checks protocol semantics without changing the JSON schema:
AWG public and preshared keys use canonical base64 for exactly 32 bytes;
endpoints have a valid host and port; addresses and allowed networks use valid
CIDRs; junk bounds are ordered and header values are distinct. DNS addresses,
port-hop ranges and calendar expiry must be valid. Refusals report categories
without credential values. Public examples use deterministic synthetic keys.

## `ripdpi.schema_version`

Integer.  Currently `1`.  The RIPDPI client rejects (ignores) a `ripdpi` block
whose `schema_version` it does not recognise.

**Additive evolution stays at version 1.** Every field added after the initial
release — `cohort_fingerprint`, `salamander_upstream_tag`, `topology`,
`expires` — is *optional and additive*: an old client ignores it, a new client
reads it, and both keep working. Only a **breaking** change (renaming or
removing a field, changing a type, tightening a required set) bumps
`schema_version` to `2`, and the client parser must learn version `2` *before*
the server starts emitting it. The `x-contract-version` integer in the schema
is the cross-repo pin: the server contract test and the client both assert it
equals the version they support.

## `ripdpi.payload_failover`

Optional payload health and quality policy for the RIPDPI imported selector runtime. Set
`client_payload_failover` in the contributing Ansible group/profile variables;
every selected host must resolve to the same policy. The emitter refuses
conflicting policies or a policy without proxy candidates. Standard sing-box
exports do not include this field: their `urltest` remains a HEAD/RTT check,
which does not establish useful payload transfer.

```yaml
client_payload_failover:
  schema_version: 2
  selector_tag: select
  probes:
    - url: https://control-a.example.test/__throttle_probe?bytes=262144
      expected_bytes: 262144
      sha256: b1882646e3ee80170bd9207304f77c71d388b0a786d53e5e7f4e16fb22e8b6dc
    - url: https://control-b.example.test/__throttle_probe?bytes=262144
      expected_bytes: 262144
      sha256: b1882646e3ee80170bd9207304f77c71d388b0a786d53e5e7f4e16fb22e8b6dc
  interval_seconds: 60
  timeout_seconds: 10
  failure_threshold: 2
  recovery_threshold: 2
  cooldown_seconds: 120
  max_backoff_seconds: 900
  quality:
    max_pass_bytes: 2097152
    max_window_bytes: 16777216
    window_seconds: 3600
    minimum_gain_percent: 20
    maximum_loaded_latency_increase_ms: 50
```

Replace both illustrative URLs with separately operated HTTPS origins serving
the exact canonical body described in [the probe runbook](../how-to/payload-throttle.md).
These example domains are not working services. The repository does not enable
this policy by default. Provisioning and accepting control origins is a separate
live operation. HTTPS certificate verification remains required; redirects,
short bodies and digest mismatches do not pass. A successful control can qualify
a candidate when the other control is unavailable; failure requires both
controls to fail through that same candidate.

Each probe requires 32768–1048576 bytes and a lowercase SHA-256 digest. Origins
must differ after host/port normalization. URLs are ASCII HTTPS without userinfo
or fragments. Bounds are: interval 30–3600 seconds, per-control timeout 1–30,
failure/recovery thresholds 2–10, cooldown 30–3600, maximum backoff 60–3600.
Timeout cannot exceed the interval; maximum backoff cannot be below it. Unknown
fields and invalid input refuse the policy instead of silently dropping it.

The nested policy accepts only version 2; version 1 must be migrated before
refresh. The enclosing bundle version remains unchanged. Omitting `quality`
retains health-only selection. With quality enabled, each origin must also
answer HEAD with status 200 and its exact Content-Length. Baseline and loaded
request latency include the complete control transaction; neither is RTT.
Verified GET body bytes divided by positive monotonic body duration establish
goodput. Loaded latency requires a concurrent HEAD fully inside that body
interval. A fast transfer may produce partial evidence, which cannot promote a
candidate on quality alone.

Quality bounds are: pass allowance 65538–16777216 bytes, window allowance
65538–268435456 bytes, window duration 60–86400 seconds, minimum gain 5–100
percent and allowed loaded-latency increase 0–2000 ms. The window allowance
must cover the pass allowance and its duration must cover the probe interval.
The pass allowance must cover twice the sum of both `expected_bytes + 1`
reservations. Reservations precede network I/O, survive failures, cancellation,
restart, network and policy changes, and expire conservatively after reboot.
They bound application body bytes, not TLS, tunnel or retransmission overhead.

A pass compares the active member and one rotating challenger using the same
origin. Promotion requires repeated complete measurements: either the required
goodput gain without exceeding the loaded-latency allowance, or a loaded-latency
reduction meeting the same percentage threshold with non-regressing goodput.
Existing recovery
threshold and cooldown still apply. Partial, stale or deferred evidence stays
visible without authorizing a quality switch. Ordinary health recovery still
requires verified payload reachability; all-candidate failure retains the last
proxy and never selects direct. REALITY uses the existing Xray candidate
runtime; AWG is outside this selector pool. Plain sing-box URLTest remains
RTT-only.

This policy applies to full imported selector profiles; the simple seeded-profile
import surface explicitly refuses it. Upgrade the paired recipient before
publishing version 2. The paired `contract/ripdpi-bundle.payload-failover.json`
fixture contains synthetic emitted input for parser agreement, not live
acceptance evidence. No policy or control endpoint is deployed by this change.

## `ripdpi.amneziawg`

Array of AWG device-VPN entries.  Empty array (`[]`) when AmneziaWG is not
enabled for the selected profiles. Enabled AWG requires a unique bound device
under `amneziawg_secrets.instances[].peers`; absence refuses the whole payload.
Use `AWG_HOST=provider:env` for multiple enabled hosts and `AWG_INSTANCE=name`
for multiple matching instances. The endpoint and parameters come from that
instance, using the same resolver as the standalone and liveness clients.

### AWGEntry fields

```jsonc
{
  "tag":     "p2-awg-<client>",      // stable identifier; matches naming convention
  "address": ["10.66.66.2/32", "fd42:42:42::2/128"], // typed device identities, IPv4 then IPv6
  "dns":     ["1.1.1.1", "1.0.0.1"],
  "mtu":     1420, // integer 1280..1420, resolved once for every consumer

  // AmneziaWG obfuscation parameters — must match the server awg0.conf exactly.
  // Resolved with three-level precedence (SOPS > cohort YAML > hard default):
  //   jc=4  jmin=40  jmax=70  s1=50  s2=100  (H1..H4 have no hard default)
  "jc":   4,
  "jmin": 40,
  "jmax": 70,
  "s1":   50,
  "s2":   100,
  "h1":   <integer>,
  "h2":   <integer>,
  "h3":   <integer>,
  "h4":   <integer>,

  // I1..I5 — special-junk packet definitions, lowercase-hex STRINGS (the
  // client parses them as strings and the schema types them ^[0-9a-f]+$).
  // Present only when configured in SOPS or the cohort YAML; omitted when absent.
  "i1": "<hex>",   // optional
  // ... i2..i5 follow the same rule

  // Fingerprint of the resolved obfuscation parameter set above (see below).
  "cohort_fingerprint": "sha256:<64-hex>",

  // The bundle carries no client private key. An operator recovery copy is encrypted in SOPS.
  // This flag tells the RIPDPI client to substitute the locally-stored key.
  "private_key_placeholder": true,

  "peer": {
    "public_key":           "<server WireGuard public key>",
    "preshared_key":        "<per-peer PSK from SOPS>",
    "endpoint":             "<server_ipv4>:<listen_port>",
    "allowed_ips":          ["0.0.0.0/0", "::/0"],
    "persistent_keepalive": 25
  }
}
```

### Cohort fingerprint

`cohort_fingerprint` is a SHA-256 over the resolved AWG obfuscation parameter
set for this entry — the values the client and the server `awg0.conf` **must
agree on byte-for-byte** or the AmneziaWG handshake stalls / fails. It lets the
client detect that disagreement *before* connecting and tell the user "profile
outdated, refresh your subscription", instead of surfacing a silent stall (per
`docs/reference/awg-cohorts.md`, a cohort mismatch shows up as "occasionally stalls, 3–4
retries" in the lucky case and a full handshake failure in the unlucky one).

Canonical pre-image (UTF-8, no trailing newline):

```
jc=<jc>&jmin=<jmin>&jmax=<jmax>&s1=<s1>&s2=<s2>&h1=<h1>&h2=<h2>&h3=<h3>&h4=<h4>&i1=<i1>&i2=<i2>&i3=<i3>&i4=<i4>&i5=<i5>
```

Each numeric value is base-10 with no leading zeros; each `i`-value is its
lowercase-hex string, or the empty string when absent. The fingerprint is
`"sha256:" + hex(sha256(pre-image))`. The **one** implementation is
`scripts/ripdpi_cohort_fingerprint.py` (called by `emit-bundle.sh` and pinned
by the contract test); the client reimplements the identical algorithm and
`contract/cohort-fingerprint.golden.json` — committed identically in both repos
— guarantees the two implementations agree.

### Private-key handoff

`scripts/new-client.sh` generates the client private key and stores it in the
SOPS-encrypted `client_registry.<device>.awg_private_key` field. The command
emits enrollment metadata, not a plaintext key or a ready-to-import AWG file.
The standalone `emit-awg.sh` configuration contains the literal
`PrivateKey = <CLIENT_PRIVATE_KEY>`. The bundle also carries no key.
`private_key_placeholder: true` tells the RIPDPI client to use its secure local
key store. A new device needs a separate manual key handoff before AWG can connect.

For an authorized handoff, the operator selects the device's encrypted registry
entry through the existing private SOPS recovery process. Check its exact
provider, environment and instance binding and verify that the public key
derived from this private key matches that instance's device peer. Deliver
only the selected device key through an approved encrypted out-of-band channel
or an in-person QR scan. Keep plaintext out of terminal recordings, agent
sessions, logs and shared documents. For a standalone client, replace the
placeholder only in the private recipient copy before import; for RIPDPI,
import the key into the device's secure local store.

The current issuer does not automate this handoff or create plaintext files
under `secrets/local/clients/**`. After delivery, the device-local key is primary;
the encrypted registry copy permits recovery without rotating the peer. Never
put the client private key into a distributed bundle or commit it.

An operator may validate a locally materialized Android artifact without
relaxing the distribution contract:

```bash
python3 scripts/validate-bundle.py --runtime-materialized /path/to/embedded-relay-bundle.json
```

This explicit mode validates each inline AmneziaWG private key, removes it only
from an in-memory copy, and then applies the unchanged redacted schema. It does
not print the key, rewrite the artifact, or make the materialized file suitable
for distribution. The file must be an owner-controlled regular file with mode
`0600`, and every component of its path must be free of symlinks and unsafe
writable directories. This local, transient artifact is the narrow exception
to the SOPS input gate; remove it immediately after validation.

### Private-key recovery flow

`private_key_placeholder: true` means the bundle carries **no usable private
key**. The client substitutes the device-local key. This section specifies what
the client does when that local key is *not* available — first launch after a
fresh install, a device migration, a cleared app data store, or a key the user
never imported. Without a spec the client "closes the gap however" and may fail
deep in AWG config parsing with an opaque error.

The client resolves the key in this order and surfaces one of these states
(stable string codes the diagnostics layer and UI key off; they are part of the
contract):

| State / code | Condition | Client behaviour |
|---|---|---|
| `KEY_PRESENT` | `private_key_placeholder=true` **and** a local key for this peer exists | Use it; connect normally. |
| `KEY_MISSING_REPROVISION` | placeholder `true`, no local key found | Do **not** fail in the parser. Import the profile in a disabled state and prompt: "This profile needs your AmneziaWG private key — re-import it (QR / Signal) to activate." The subscription itself remains valid. |
| `KEY_REJECTED` | a local key exists but the server rejects the handshake (wrong/rotated key) | Surface "key no longer matches this server — request re-provisioning"; keep the profile, do not delete it. |
| `PLACEHOLDER_ABSENT_NO_KEY` | `private_key_placeholder` is absent/false **and** no inline `private_key` | Treat as a malformed AWG entry and skip it (existing lenient-parser behaviour). |

The recovery action for `KEY_MISSING_REPROVISION` / `KEY_REJECTED` is the same
out-of-band channel as the initial handoff: the operator retrieves the key
from its existing device-local store or the SOPS recovery copy, checks the
current binding and peer key, then follows the manual handoff above. Recovery
of the same current key does not change the bundle. If the peer was rotated or
revoked, use the current provisioning contract instead of restoring an old key.

## `ripdpi.hysteria_extras`

Object keyed by the exact Hysteria2 outbound `tag` that `emit-singbox.sh`
emits for this host (`"p2-hysteria2-<provider>-<env>"`).  Empty object (`{}`)
when Hysteria is not enabled or has no extras to convey.

The RIPDPI client uses these extras to configure transport-layer properties
that the standard sing-box Hysteria2 outbound schema does not expose in the
subscription format.

### HysteriaExtras fields

```jsonc
{
  // Always present.
  "insecure": false,

  // Present only when hysteria.salamander_enabled = true in SOPS.
  "obfs": {
    "type":     "salamander",
    "password": "<hysteria.salamander_password from SOPS>"
  },

  // The upstream Hysteria2 release whose Salamander algorithm this server runs
  // (= hysteria.version from SOPS).  Present only alongside salamander obfs.
  "salamander_upstream_tag": "v2.9.0",

  // Hopping policy for the qualified native RIPDPI client.
  // ports is the range string "low:high"; interval is the hop cadence.
  "port_hopping": {
    "ports":    "20000:50000",
    "interval": "30s"
  }
}
```

`insecure: false` is always present and non-negotiable.  The RIPDPI client
treats a missing or `true` value as a configuration error and refuses to connect.

`salamander_upstream_tag` lets the client compare the server's Salamander
algorithm version against the one its bundled obfuscator implements. Salamander
can change between Hysteria2 releases; on a skew the client warns the user
("obfuscation may not match this server — update the app") instead of failing
the handshake opaquely. It reuses the existing `hysteria.version` secret — no
new key to keep in sync.

## `ripdpi.topology`

Declares the transport topology the client cannot infer from the flat
`outbounds` list, so it can tell a split-hop or realm-relayed endpoint from a
direct one rather than mis-modelling a dual-role flow.

```jsonc
{
  // true when this endpoint is the entry of a two-VPS split-hop topology
  // (entry and egress are different hosts). The client must NOT assume the
  // egress IP equals the endpoint IP — relevant against per-IP DPI classifiers.
  "split_hop_egress": false,

  // realm/relay id when the Hysteria2 endpoint is reached via a STUN/NAT
  // realm relay rather than directly; null when direct.
  "hysteria_realm": null
}
```

`split_hop_egress` is sourced from `vpn.enable_split_hop_ingress`: that role
runs on the client-facing Node A whose upstream path exits through Node B.
`hysteria_realm` remains explicit `vpn.hysteria_realm` metadata because the
enable toggle alone does not define a stable realm identifier. Both default to
the direct-deployment values (`false` / `null`). Pure egress roles (e.g.
`warp-outbound`) are server-side only and intentionally absent — the client has
no half to play there. Multi-host emission aggregates every entry rather than
trusting `HOSTS` order: any ingress host makes `split_hop_egress=true`, the
first non-null realm identifier is retained, and conflicting non-null realm
identifiers fail closed.

## `ripdpi.expires`

Optional RFC-3339 / ISO-8601 UTC instant after which the subscription token
stops serving this bundle (the server returns `410 Gone`). Carried **inside**
the `ripdpi` object and atomic subscription document so the
client can warn "subscription expires in N days, refresh" proactively, instead
of only finding out when the next `/sub` fetch already failed.

`emit-bundle.sh` emits it when `BUNDLE_EXPIRES` is set. The supported issuance
path normalizes `EXPIRES` once and writes the identical UTC instant into the
authoritative subscription document (or legacy `.meta` sidecar) and the bundle's early-warning copy. Date-only
input means midnight UTC. The field is absent for non-expiring tokens:

```bash
make issue-sub-token CLIENT=phone FORMAT=ripdpi EXPIRES=2026-12-31
```

## Merge guarantee

The `ripdpi` key is appended to the RIPDPI profile document via:

```bash
jq --argjson r "$ripdpi_json" '. + {ripdpi: $r}' base.json
```

All existing keys (`log`, `dns`, `inbounds`, `outbounds`, `route`) are
preserved verbatim.  The merge does not modify, reorder, or re-encode any
profile field.

## Usage

```bash
# Single host (default upcloud:prod)
make emit-bundle CLIENT=laptop

# Multi-host
HOSTS="upcloud:prod,hetzner:prod" make emit-bundle CLIENT=laptop

# With explicit cohort and AWG cohort slug
HOSTS="upcloud:p0,upcloud:p1p2" COHORTS="p0,p1p2" AWG_COHORT=narrow-junk-sequential \
  make emit-bundle CLIENT=phone

# Per-app routing flags are forwarded to the profile emitter
scripts/emit-bundle.sh phone --per-app-via-tun com.example.private
```

The output is written to stdout so the caller can redirect it, pipe it through a
QR encoder, or POST it to a subscription host.

### Hysteria ECH and BBR recipient boundary

ECH-required Hysteria profiles currently target official sing-box 1.14.3 only.
`emit-bundle` refuses them before output because the RIPDPI consumer has no
qualified ECH parser/connection contract. The existing bundle schema/version is
unchanged; public ECH configuration is never silently stripped. Use the canonical
`emit-singbox` format for the supported ECH recipient. Private ECH keys never
belong in either artifact.
The new BBR recipient profiles use the same qualified official engine and also
refuse RIPDPI export. The bandwidth-capped classical profile remains supported.


Hysteria port hopping requires the qualified native RIPDPI client. The emitter
retains `hysteria_port_range` as standard `server_ports` and matching extras,
with the same fixed `hop_interval`. The interval uses whole seconds, minutes or
hours, from 5 seconds through 9223372036854 milliseconds. Invalid policy fails
before output. The scalar `server_port` does not widen the hopping set. Older
clients do not satisfy this contract. Official sing-box output retains its
existing policy. Multi-host output includes extras for every Hysteria tag,
independently of host order.
Full bundle validation requires each hopping extra to match one Hysteria
outbound by tag. When standard hopping fields are also present, their port set
and effective interval must agree after normalization. Either policy form alone
and standalone extension validation remain supported.

### Dual-stack device contract

AWG `address` contains exactly two canonical host CIDRs, IPv4 /32 followed by
IPv6 /128. Encrypted peers use `allowed_ips.ipv4` and `allowed_ips.ipv6`; both
must belong to their selected instance pools. The single-CIDR secrets contract
is removed. `mtu` is an integer from 1280 through 1420, resolved from instance,
technical cohort and role defaults. Both fields are required before publication.
The wire array and schema version stay unchanged; consumers must adopt the
stricter admission with the canonical vendored schema. Consumer integration is
tracked by `po4yka/RIPDPI#DAT-1792081130689287`.
