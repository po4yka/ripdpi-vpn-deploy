## Context

See proposal.md. `warp-outbound` is a tactical role; it runs the vendor client in `tunnel_only` inside the owned `ripdpi-warp` namespace and only uses an existing registration (`activate.yml` runs `warp-cli registration show` and never `registration new`).

## Goals / Non-Goals

- Goal: one tracked cohort that a disposable node can switch to after its first `device-full-staging` onboarding.
- Non-goal: automating WARP registration, or enabling WARP on any production profile.

## Decisions

- Copy `vpn-device-full-staging` and change two keys, rather than an extra-vars escape hatch: the controller deliberately reads the `vpn` map only from tracked cohorts.
- One narrow route (`full:www.cloudflare.com`) makes the normalizer select the WARP backend; the refresh check needs the backend, not real recipient traffic.
- First onboarding stays on `device-full-staging`, because the disposable onboarding intent admits only that cohort.

## Contracts and ownership

- `ansible/group_vars/vpn-device-full-warp-staging.yml`, `ansible/role-tiers.yml`, docs tables, profile tests.

## Risks / Trade-offs

- The first WARP deploy stops at the registration check until the operator registers once → documented in `deploy-profiles.md`; registration needs explicit owner authorization because it creates a vendor account.

## Migration Plan

Additive. Rollback: revert the commit.
