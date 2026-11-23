## Purpose

Give disposable staging a tracked cohort that runs the WARP outbound backend on the device-full-staging transports, so the WARP namespace refresh can be accepted on a real node.

## ADDED Requirements

### Requirement: REQ-WARP-STAGING-COHORT — WARP staging cohort mirrors device-full-staging

The `vpn-device-full-warp-staging` cohort MUST equal the `vpn-device-full-staging` `vpn` map except `enable_warp_outbound: true` and exactly one `warp_outbound_routes` entry, and MUST keep the same generated staging `public_site_canonical_url`.

#### Scenario: Profile maps compared

- **WHEN** the profile guard test loads both cohort files
- **THEN** the maps differ only in the WARP toggle and its one route, and the staging origin is the same

### Requirement: REQ-WARP-STAGING-FAMILY — Cohort is a guarded family profile

The cohort MUST be listed in `role-tiers.yml` `family_profiles`, so the deploy profile lint refuses any research role in it.

#### Scenario: Family list

- **WHEN** `scripts/check-deploy-profile.py` runs
- **THEN** it checks the new cohort with the other family profiles and passes

### Requirement: REQ-WARP-STAGING-ONBOARDING — Onboarding intents admit the WARP cohort

A disposable onboarding intent MUST admit cohort `device-full-staging` or `device-full-warp-staging` and MUST refuse any other non-CI cohort. Intent preparation MUST take the cohort from the required `PROMOTION_COHORT` input and MUST refuse when it is missing.

#### Scenario: WARP cohort intent

- **WHEN** an operator prepares an intent with `PROMOTION_COHORT=device-full-warp-staging`
- **THEN** the published intent names that cohort and passes the intent validator

#### Scenario: Foreign or missing cohort

- **WHEN** `PROMOTION_COHORT` is missing or names another cohort such as `device-full`
- **THEN** preparation refuses and publishes nothing
