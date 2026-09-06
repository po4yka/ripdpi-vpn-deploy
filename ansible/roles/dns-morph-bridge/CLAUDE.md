# role: dns-morph-bridge — P4 bootstrap-channel listener on UDP/53

## Design decisions

**Config validation is role-specific** — the unpublished bridge binary has no
stable validation CLI. The shared bounded YAML validator rejects malformed or
duplicate-key candidates and invalid nested listener, forwarder, morph, limit,
or log values before publication; the restart handler then proves liveness.

**Standalone listener, not an Xray inbound** — DNS-Morph requires line-rate
packet inspection of every UDP/53 datagram to split handshake-shaped queries
from probe traffic, then re-stitch fragmented payloads. That logic does not
fit any existing P0/P1/P2 transport's plugin surface, so the bridge runs as
its own systemd unit and only the *decoded* fragments are stitched into an
upstream data-plane endpoint (`dns_morph_bridge.upstream_endpoint`).

**UDP/53 is forced open; everything else is an attack surface** — UDP/53
must be reachable for the bridge to receive client handshakes, but the same
port attracts indiscriminate scanner traffic. The role co-installs unbound on
127.0.0.1:5353 and the bridge forwards every non-handshake query verbatim so
an active probe sees a normal recursive resolver, not silence.

**No default binary URL** — the reference daemon has no released artifact
the role can fetch. Operators publish a self-built binary to a trusted
artifact store and point `dns_morph_bridge_secrets.binary_url` +
`.binary_sha256` at it. The pre-flight assert fails closed when either is
missing.

**Co-residency with the full stack** — UDP/53 does not collide with any
other transport's port. The role can be enabled alongside P0/P1/P2 on the
same VPS; the only constraint is `events_per_minute_max` being set high
enough to absorb the scanner volume that comes with a public resolver.

## What's done well

- **Shared runtime publication** — the bridge artifact SHA256 is also its
  immutable release identity. `runtime-release` verifies the bytes, records a
  receipt, and publishes the configured binary link with rollback compensation.
- **Localhost recursor isolated from the public listener** — unbound binds
  127.0.0.1:5353 only; the bridge is the sole public listener. No risk of
  the recursor becoming an open resolver if the bridge crashes.
- **Per-minute event cap on the probe-defense path** — handshake-shaped
  queries bypass the cap so legitimate clients are never throttled by
  scanner storm. See `defaults/main.yml`.

## Pitfalls

- **Recursor port collision** — if the host already runs systemd-resolved
  on 127.0.0.53:53, unbound on 127.0.0.1:5353 is fine, but if the operator
  has already moved systemd-resolved to 5353 the bind fails. Verify
  `ss -lnu` before enabling.
- **RU "trusted DNS" routing** — RU client devices increasingly route DNS
  through carrier-provided resolvers, which may never see the bridge. The
  bootstrap channel only works when the client app uses the bridge's IP as
  its resolver directly, not the system resolver. Document this in the
  linked client task.
- **UDP/53 reflection-attack risk** — a public recursor is an amplification
  vector. The role configures unbound with `access-control: 0.0.0.0/0
  refuse` so external clients cannot recurse through it; only the bridge's
  active-probing-defense path forwards to the recursor. Do not relax this
  setting "for testing".
- **Bridge signing-key rotation invalidates every client** — clients pin
  the bridge's public key in their bootstrap config. Rotating the key
  requires re-shipping every client config; treat the key as long-lived
  and rotate only on compromise.
