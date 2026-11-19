## Context

The `vpn-acceptance` skill defines scoped evidence for staging. Staging and the client device are real infrastructure and need operator authorization at run time (AGENTS.md decision boundaries).

## Goals / Non-Goals

- One reproducible acceptance run that covers all five links of the chain.
- Non-goal: load or long-duration testing, or production verification.

## Decisions

- Use the existing staging node and a named, reusable Pixel or emulator instance; list existing instances before creating one. Rejected: a new instance per run.
- Assumption: the block is applied with a temporary nftables rule on the staging node and removed by the same script; the node is disposable.
- Assumption: the hourly reporting window is shortened by a debug flush in the client build; if R3 has no such flag the run waits for the window and the evidence records it.
- Assumption: RIPDPI R2 is `DGN-1795085357320979`, R3 is `DGN-1795085498592630` and R4 is `DAT-1795085420746769` (IDs supplied by the coordinator, in `po4yka/RIPDPI`; R1 is not yet linked). They are recorded in `status_detail` as an external gate rather than `blocked_by`, because federation needs a peer checkout to resolve them; move them to `blocked_by` as qualified IDs when a peer checkout is available.

## Contracts and ownership

- A how-to in `docs/how-to/`, the verification file. No source code changes in this repository.

## Risks / Trade-offs

- Staging block leaves a rule behind -> the procedure removes it and verification records the removal.
- Client build mismatch -> the app version and bundle version are recorded.

## Migration Plan

No migration. Rollback is removing the temporary firewall rule and the staging bundle.
