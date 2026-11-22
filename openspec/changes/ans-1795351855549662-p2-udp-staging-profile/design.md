# Design: p2-udp disposable staging profile

## Context

The deployment controller replaces the canonical `vpn` map with the host cohort's map and reads no host vars; extra vars refuse `vpn`. A role toggle can therefore change only through a tracked cohort file. `vpn-device-full-staging` is the precedent: the device-full transports with monitoring, watchdog and backup off.

## Decisions

- Copy the `vpn-p2-udp` map key for key and change only the three toggles. A test compares the two maps, so a later p2-udp transport change must reach the staging profile too. A complete `device-full-staging` style map would add keys that `vpn-p2-udp` leaves to role defaults and so would stage a different configuration.
- Keep the profile in `family_profiles`. It enables no research role, and the family guard then prevents one from being added.
- Use the repository's generated origin expression (`transport_semantics.PUBLIC_ORIGIN_TEMPLATE`) for `public_site_canonical_url`. `scripts/ci-bootstrap-secrets.sh` writes the same origin to `hysteria.masquerade_url`, so the Hysteria equality assert passes without an extra-vars origin. The self-origin assert compares the origin host with `hysteria.server_name`, which staging secrets do not set. With `hysteria_public_site_dir` the masquerade is a `file` origin and the URL is only the site identity.
- Do not relax watchdog, monitoring or backup validation and do not add staging fields to the secrets generator: the roles are off, so their inputs are not read.

## Rejected

- Toggle overrides through `ANSIBLE_EXTRA_VARS_FILE`: the controller refuses the `vpn` key by design.
- Generate a Hysteria `watchdog` client and canary URL in staging secrets: the canary must be operator-owned HTTPS, and watchdog acceptance is not in scope.

## Risks

- `make dry-run` reads no promotion config, so a bootstrapped disposable node rendered with `COHORTS=p2-udp-staging` can dry-run directly. A real `make deploy` of a fresh node still needs the disposable onboarding intent, which admits only `device-full-staging`; extending that intent is separate work.
- The Terraform `public_listeners` of the staging node must match the p2-udp manifest, including the `hysteria-masquerade` TCP entries, or the listener contract check refuses before host changes.
