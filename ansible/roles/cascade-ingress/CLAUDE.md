# role: cascade-ingress — client-facing classifier owner

## Design decisions

The role owns the disabled client-termination integration contract and the tri-state classifier interface. It renders the private egress-leg scaffold but exposes no foreign-facing tunnel listener and has no service-start task. The unchanged SHA256-pinned geodata role output at `geoip.dat` is the only production dataset source.

## What's done well

- Dataset preflight runs before the integration contract or tunnel scaffold is rendered.
- The integration contract names all three outcomes and has no fallback; live per-connection consumption requires a later behavior-tested adapter and governance decision.
- Secret-bearing WireGuard configuration uses `no_log`, `diff: false`, and mode `0600`.
- The nftables namespace is role-scoped and distinct from split-hop.

## Pitfalls

- `dataset-unavailable` is a serving hard-block, never a synonym for `foreign`.
- Do not add a service-management toggle while the classifier consumer is only a disabled integration contract.
- Do not import split-hop responder, keepalive, conntrack-direction, or no-listen invariants; they defend a different threat model.
