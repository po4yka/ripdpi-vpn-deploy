## Context

Protocol-level liveness, quorum evaluation, redacted persistence, alerting, and
operator-gated spare promotion already exist. The gap is complete recurring
adoption and observed filtered-path evidence for all profiles.

## Goals / Non-Goals

- Goal: make control-plus-filtered evidence recurring and complete.
- Goal: preserve explicit uncertainty and recovery transitions.
- Non-goal: automate promotion or encode provider, carrier, or geographic identities.

## Decisions

- Extend the existing evaluator and schedule instead of introducing a second monitor.
- Treat a missing required vantage as unknown, never success or censorship.
- Keep technical path-class aliases and redacted categorical evidence only.
- Require sustained quorum and a final recheck before issuing the existing operator decision.

## Contracts and ownership

- Monitoring owns evaluation, persistence, and alerting.
- Operator configuration owns sentinel access and remains outside Git.
- Rotation consumes the evaluator verdict but cannot weaken its evidence contract.

## Risks / Trade-offs

- Vantage outages may reduce availability of decisions; fail closed as unknown.
- Recurring checks add load; preserve bounded schedules and authenticated lightweight probes.
- Correlated vantages can create false confidence; acceptance requires independent path classes.

## Migration Plan

Validate all profiles in staging, observe an unavailable-vantage transition and
recovery, then enable the recurring gate. Rollback disables the schedule without
changing deployed profile configuration.
