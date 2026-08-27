# network-exposure-gate — reviewed firewall intent

## Design decisions

- The controller validator owns schemas, canonical digest, RSA signature,
  separately pinned public-key trust, expiry and exact-host promotion.
- This role never changes a managed host. The firewall remains the only
  renderer; disabled and log-only modes pass an empty enforcement plan.
- Artifacts stay outside Git. All metadata and directional policy are signed;
  promotion binds the complete signed artifact bytes, not just its ranges.

## What's done well

- Validation executes in check mode before any firewall mutation.
- The internal plan and controller paths stay behind no_log. Only categorical
  validation, source identifier, directional counts, and digests are reported.
- Disabled mode clears stale facts and needs no artifact, key, or OpenSSL.

## Pitfalls

- A key supplied by the artifact is not a trust anchor; use the independently
  configured DER public-key SHA-256 fingerprint.
- Applied rules do not auto-expire. Revert to disabled and explicitly apply
  the canonical firewall before the artifact deadline; never add an updater.
- Ingress matches source addresses; host egress and forwarded traffic match
  destinations. They must never inherit one another's prefixes.
- Log-only review invokes only this role. A full site deployment still owns
  baseline firewall convergence and is not the non-mutating review command.
