## Context

See proposal.md. `warp-outbound` is a tactical role; it runs the vendor client in `tunnel_only` inside the owned `ripdpi-warp` namespace and only uses an existing registration (`activate.yml` runs `warp-cli registration show` and never `registration new`).

## Goals / Non-Goals

- Goal: one tracked cohort that a disposable node can onboard into for the WARP refresh check.
- Non-goal: automating WARP registration, or enabling WARP on any production profile.

## Decisions

- Copy `vpn-device-full-staging` and change two keys, rather than an extra-vars escape hatch: the controller deliberately reads the `vpn` map only from tracked cohorts.
- One narrow route (`full:www.cloudflare.com`) makes the normalizer select the WARP backend; the refresh check needs the backend, not real recipient traffic.
- The disposable onboarding intent admits `device-full-warp-staging` beside `device-full-staging`, selected by a new required `PROMOTION_COHORT` preparation input. A first staging run showed that switching an onboarded node to this cohort cannot pass promotion: the cohort changes the deployable digest, the executor binding pins the hash of the liveness configuration that carries that digest, and only an onboarding intent creates a new binding. Both cohorts keep all four profiles, so the intent's four-profile policy, AWG target and inventory-membership checks stay unchanged. The input is required rather than defaulted, so an intent never names a cohort the operator did not choose.

## Contracts and ownership

- `ansible/group_vars/vpn-device-full-warp-staging.yml`, `ansible/role-tiers.yml`, docs tables, profile tests.
- `scripts/disposable_promotion.py` owns the admitted cohort set; `scripts/prepare-disposable-promotion-intent.py` takes `PROMOTION_COHORT` through the isolated Make target.

## Risks / Trade-offs

- The first WARP deploy stops at the registration check until the operator registers once → documented in `deploy-profiles.md`; registration needs explicit owner authorization because it creates a vendor account.

## Migration Plan

Additive. Rollback: revert the commit.
