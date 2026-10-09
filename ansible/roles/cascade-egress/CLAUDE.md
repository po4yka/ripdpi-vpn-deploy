# role: cascade-egress — tunnel termination and forwarding

## Design decisions

The role owns only the private cascade-leg listener and forwarding configuration scaffold. It has no classifier input, dataset path, client profile, destination-policy knowledge, or service-start task.

## What's done well

- Tunnel secrets render with `no_log`, `diff: false`, and mode `0600`.
- The nftables namespace is role-scoped and distinct from cascade ingress and split-hop.

## Pitfalls

- Do not add GeoIP, RU/foreign, or client-termination decisions here; classification belongs exclusively to cascade ingress.
- Service management remains off until a future attestation-backed activation decision.

- Ordinary site convergence always invokes lifecycle reconciliation. The
  `cascade_egress_role_enabled` input selects enable or owned runtime retirement before
  secret/package guards. Disable stops units and removes only declared authority;
  shared packages, immutable runtime receipts, historical logs and recovery data
  remain available for a later explicit recovery.

Disable preserves the same historical-ownership refusal boundary as inert
convergence. An active/residual historical tunnel or policy is not adopted or
deleted; only a clean inactive implementation scaffold can retire its files.
