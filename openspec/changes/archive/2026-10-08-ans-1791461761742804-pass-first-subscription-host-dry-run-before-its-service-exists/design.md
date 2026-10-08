## Context

Check mode plans the service template without creating it. The existing firewall recovery role handles this boundary with explicit systemd LoadState discovery.

## Goals / Non-Goals

- Goal: complete first P1 dry-run with exact planned-unit guards.
- Non-goal: skip loaded services or change authentication, listeners or service hardening.

## Decisions

- Register the template result; query LoadState only in check mode with a read-only command forced to run.
- Accept loaded/not-found and the existing bounded return-code contract only.
- Require a planned template change for not-found. Defer only that activation. Real deployment remains unconditional.

## Contracts and ownership

- Primary writer owns subscription-host tasks, its instructions, focused tests and this change. Live source/inventory use one lane.
- No Terraform, script, vpnd, secrets or protocol contract changes.

## Risks / Trade-offs

- Discovery errors cannot authorize deferral; boundary tests cover failure and unknown state.
- Local tests supplement actual first-host dry-run and deploy; no fixtures substitute for live proof.

## Migration Plan

Validate local tests/lint/snapshots, real role convergence and exact-source CI. Repeat the actual P1 dry-run before deploy/verify/security and authenticated XHTTP. This regression uses the already authorized fresh permanent node rather than another paid staging. Failed dry-run stops deployment; reverting source leaves runtime unchanged.
