## Context

The `vpn-acceptance` skill defines scoped evidence for staging. Staging and the client device are real infrastructure and need operator authorization at run time (AGENTS.md decision boundaries).

## Goals / Non-Goals

- One reproducible acceptance run that covers all five links of the chain.
- Non-goal: load or long-duration testing, or production verification.

## Decisions

- Use the existing staging node and a named, reusable Pixel or emulator instance; list existing instances before creating one. Rejected: a new instance per run.
- The block is one rule in its own `inet ripdpi_acceptance` table with an input hook before the managed firewall table, applied and removed by `scripts/field-analytics-block.sh`; removal deletes the whole table, so the managed ruleset is never edited. `SOURCE` can limit it to the test device. Rejected: editing the firewall role's table, which the role replaces on its next converge and whose rollback the role owns.
- Assumption: the hourly reporting window is shortened by a debug flush in the client build; if R3 has no such flag the run waits for the window and the evidence records it.
- Assumption: RIPDPI R2 is `DGN-1795085357320979`, R3 is `DGN-1795085498592630` and R4 is `DAT-1795085420746769` (IDs supplied by the coordinator, in `po4yka/RIPDPI`; R1 is not yet linked). They are recorded in `status_detail` as an external gate rather than `blocked_by`, because federation needs a peer checkout to resolve them; move them to `blocked_by` as qualified IDs when a peer checkout is available.

## Contracts and ownership

- `docs/how-to/field-analytics-acceptance.md`, the verification file, `scripts/field-analytics-block.sh` (the staging block and unblock in a private `inet ripdpi_acceptance` nftables table, plan-only unless `APPLY=1`, production refused), `scripts/field-analytics-evidence.py` (pass or fail checks of the saved ingest, alert and bundle artifacts) and their local tests in `tests/unit/test_field_analytics_acceptance.py`. No runtime role changes.

## Risks / Trade-offs

- Staging block leaves a rule behind -> the procedure removes it and verification records the removal.
- Client build mismatch -> the app version and bundle version are recorded.

## Migration Plan

No migration. Rollback is removing the temporary firewall rule and the staging bundle.
