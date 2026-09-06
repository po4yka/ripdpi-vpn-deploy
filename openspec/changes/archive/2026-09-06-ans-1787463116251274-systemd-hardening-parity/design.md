## Context

The audit compared the three internet-facing transport units and found three
distinct sandbox levels. hysteria-realm was written most recently and carries
the full baseline; hysteria predates it; snell is a research-tier unit that
was never brought up to either.

## Goals / Non-Goals

- Goals: one uniform sandbox floor for internet-facing transport daemons;
  verified by contract test plus molecule convergence.
- Non-Goals: hardening non-transport units (watchdog, backup, monitoring —
  they are localhost-bound or operator-triggered); seccomp-permitlists tuned
  per binary beyond the shared `@system-service` profile already proven by
  hysteria-realm's sing-box processes; network restrictions
  (`RestrictAddressFamilies`) left for a future pass because QUIC/UDP +
  AmneziaWG namespace interactions need live validation first.

## Decisions

### D1 — Raise to the hysteria-realm profile (chosen)

hysteria-realm runs the same upstream binary family (sing-box) under exactly
this profile in production, so the syscall filter set is field-proven for
this workload class. Raising hysteria and snell to it avoids inventing new
policy.

Rejected: per-unit minimal policies (more surface for drift, no security
benefit at this exposure level).

### D2 — Contract test pins the directive set (chosen)

A pytest contract check parses each transport unit template and asserts the
baseline directives. Molecule proves services still start; the contract test
proves parity survives future edits.

## Risks / Trade-offs

- `MemoryDenyWriteExecute=true` can break JIT-based runtimes; neither Xray,
  sing-box, nor hysteria JIT-compiles, and realm already runs this flag.
- `SystemCallFilter=@system-service` denies exotic syscalls (e.g. some io_uring
  paths); same profile already proven by hysteria-realm.
- MED risk overall: molecule scenarios for both roles run in CI on every PR
  and would catch startup failures before merge.

## Migration Plan

Single commit: two unit templates updated, contract test added, focused
molecule scenarios executed locally where Docker is available and in CI.

## Open Questions

- None.
