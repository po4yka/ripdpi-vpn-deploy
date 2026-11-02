## Context

The native Xray export already emits the typed bounded-pool profile. RIPDPI
export refuses tuning. The client has a native pool, but import does not retain
the limit and separate session factories can multiply its carrier count.

## Goals / Non-Goals

- Goal: deliver and apply the existing bounded stream-up profile without field loss.
- Goal: check a TCP reserve first after active UDP payload failure.
- Non-goal: deploy nodes, publish recipient credentials, enable a policy by default,
  change protocol pins or claim physical-device or filtered-path acceptance.

## Decisions

- Reuse `transport.xmux` with `maxConnections` from 1 through 4 and the three
  existing retirement fields set to zero. Keep exact server-version admission.
- Keep one shared client pool per endpoint backend. Do not create a new pool algorithm.
- Retain payload policy version 2 and the existing selector lifecycle. Change only
  unhealthy Hysteria2 reserve ordering; healthy quality comparison keeps its current order.
- Retain optional policy configuration. Do not invent or deploy public control URLs.
- Generate one synthetic mixed P1/Hysteria fixture through the real materializer.
  Place it with test inputs; the unchanged published schema has no new fixture dependency.

## Contracts and ownership

- Primary owns `scripts/client_payload.py`, its matching tests, new synthetic fixture,
  delivery documentation and this task. No Terraform or Ansible runtime edit is needed.
- The paired client owns import, persistence, runtime mapping, native pooling, selection
  and tests under `po4yka/RIPDPI#TRN-1793634968382224` in its own worktree.
- The producer is the only writer of the emitted fixture. The consumer copies its bytes.

## Risks / Trade-offs

- Old consumers can lose tuning. Update the paired client before distributing tuned bundles.
- Pool sharing changes lifetime. Exercise concurrency, cancellation, shutdown and replacement.
- TCP and UDP on one IP share address-wide failures. The fixture proves transport diversity only.
- Unit and local native tests do not establish filtered-network survival.

## Migration Plan

Review both PRs and install the paired consumer before enabling typed tuning for
recipients. Keep the existing untuned profile for rollback. Run targeted exporter
and consumer tests, byte parity for the generated fixture, independent review and
`build-gate -- make check` with pinned tools. Hosted CI and any future rollout have
separate evidence. This change does not authorize a live rollout.
