# role: cascade-egress — tunnel termination and forwarding

## Design decisions

The role owns only the private cascade-leg listener and forwarding configuration scaffold. It has no classifier input, dataset path, client profile, destination-policy knowledge, or service-start task.

## What's done well

- Tunnel secrets render with `no_log`, `diff: false`, and mode `0600`.
- The nftables namespace is role-scoped and distinct from cascade ingress and split-hop.

## Pitfalls

- Do not add GeoIP, RU/foreign, or client-termination decisions here; classification belongs exclusively to cascade ingress.
- Service management remains off until a future attestation-backed activation decision.
