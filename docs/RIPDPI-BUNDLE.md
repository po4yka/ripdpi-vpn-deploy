# RIPDPI Bundle — server-side schema specification

> **The executable contract is [`contract/ripdpi-bundle.schema.json`](../contract/ripdpi-bundle.schema.json)** — a JSON Schema (draft 2020-12) that is the single source of truth for the `ripdpi` object. This document is its prose companion. The schema is vendored byte-identical into the RIPDPI Android client repo and validated by a contract test in **both** CIs (`scripts/validate-bundle.py` + `tests/unit/test_bundle_schema.py` here; `RipdpiBundleContractTest` there), so the contract cannot drift silently between the two repos. When you change the shape of the `ripdpi` object, change the schema first.

## Overview

`emit-bundle.sh` (and `make emit-bundle CLIENT=<name>`) produces a single JSON
file that is the canonical subscription artifact for the RIPDPI Android client.
It is the standard sing-box document that `emit-singbox.sh` produces, extended
with a top-level `ripdpi` object carrying device-VPN and transport-obfuscation
metadata that the RIPDPI client needs but that a plain sing-box config cannot
express.

Standard sing-box clients that do not understand the `ripdpi` key treat it as an
unknown top-level field and ignore it safely.  Operators who want a
subscription artifact for those clients should use the `/sub` plain endpoint
instead of the bundle endpoint.

## Top-level structure

```jsonc
{
  // --- Everything emit-singbox.sh produces, unchanged ---
  "log":       { ... },
  "dns":       { ... },
  "inbounds":  [ ... ],
  "outbounds": [ ... ],   // includes all P0/P1/P2 outbounds + selector/urltest
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

## `ripdpi.amneziawg`

Array of AWG device-VPN entries.  Empty array (`[]`) when AmneziaWG is not
enabled for the cohort (no `amneziawg_secrets.peers` entry for this client).

### AWGEntry fields

```jsonc
{
  "tag":     "p2-awg-<client>",      // stable identifier; matches naming convention
  "address": ["10.66.66.X/32"],      // client tunnel address (from peer.allowed_ips in SOPS)
  "dns":     ["1.1.1.1", "1.0.0.1"],
  "mtu":     1420,

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

  // The client private key is NEVER stored server-side.
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
`docs/AWG-COHORTS.md`, a cohort mismatch shows up as "occasionally stalls, 3–4
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

The client private key is generated by `scripts/new-client.sh` and delivered to
the device through a secure out-of-band channel (Signal message, in-person QR
scan, encrypted notes app).  It is never written to SOPS, never committed, and
never appears in the bundle.  `private_key_placeholder: true` signals to the
RIPDPI client that it must load the key from its own secure local storage rather
than parsing it from the subscription JSON.

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
out-of-band channel as the initial handoff: the operator re-issues the key via
`scripts/new-client.sh` and delivers it over Signal/QR. The bundle never needs
to change for recovery — only the device-local key does — which is exactly why
the key is out-of-band and the placeholder exists.

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

  // Present only when hysteria_port_range is configured in group_vars.
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

Sourced from `vpn.split_hop_egress` / `vpn.hysteria_realm` in `group_vars`;
both default to the direct-deployment values (`false` / `null`). Pure egress
roles (e.g. `warp-outbound`) are server-side only and intentionally absent —
the client has no half to play there.

## `ripdpi.expires`

Optional RFC-3339 / ISO-8601 UTC instant after which the subscription token
stops serving this bundle (the server returns `410 Gone`). Carried **inside**
the `ripdpi` object — in addition to the existing `.meta` sidecar — so the
client can warn "subscription expires in N days, refresh" proactively, instead
of only finding out when the next `/sub` fetch already failed.

`emit-bundle.sh` emits it when `BUNDLE_EXPIRES` is set. Pair it with the same
date the operator gives `issue-sub-token.sh --expires` (which writes the
authoritative `.meta` sidecar and drives the `410`); the bundle field is the
*early-warning* copy, the sidecar remains the enforcement point. Absent for
non-expiring tokens. For example:

```bash
BUNDLE_EXPIRES=2026-12-31T23:59:59Z make emit-bundle CLIENT=phone
```

## Merge guarantee

The `ripdpi` key is appended to the sing-box document via:

```bash
jq --argjson r "$ripdpi_json" '. + {ripdpi: $r}' base.json
```

All existing keys (`log`, `dns`, `inbounds`, `outbounds`, `route`) are
preserved verbatim.  The merge does not modify, reorder, or re-encode any
sing-box field.

## Usage

```bash
# Single host (default upcloud:prod)
make emit-bundle CLIENT=laptop

# Multi-host
HOSTS="upcloud:prod,hetzner:prod" make emit-bundle CLIENT=laptop

# With explicit cohort and AWG cohort slug
HOSTS="upcloud:p0,upcloud:p1p2" COHORTS="p0,p1p2" AWG_COHORT=narrow-junk-sequential \
  make emit-bundle CLIENT=phone
```

The output is written to stdout so the caller can redirect it, pipe it through a
QR encoder, or POST it to a subscription host.
