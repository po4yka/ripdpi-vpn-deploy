# Change: Repair deployment readiness runtime defects

Task ID: `ANS-1792499727513191`

## Why

A pre-deployment audit of `main` found five runtime defects that a production
rollout would expose:

- Daily Xray log rotation restarts Xray directly on every production profile
  except `vpn-device-full-staging`. The profiles replace the canonical `vpn`
  map and omit `enable_transport_egress`, so the template default selects the
  unguarded branch. The guarded generation controller then sees a changed
  frontend process and restarts the complete protected generation. P0, P1 and
  Hysteria go down once each day.
- The AmneziaWG role installs `resolvconf`. On a Debian 13 host with
  `systemd-resolved`, apt removes `systemd-resolved` and `libnss-resolve`, and
  the host resolver that the baseline role manages stops working.
- Forwarded AmneziaWG traffic has no destination filter. An authenticated
  device can reach the provider metadata service and private ranges that the
  Xray and Hysteria egress boundary already refuses.
- The watchdog restarts nginx or recovers Xray after configuration validation
  fails. The restart then stops a running service that has a good in-memory
  configuration.
- The Hysteria version pin accepts pre-release tags on every profile. The Xray
  pin already requires an exact stable `vMAJOR.MINOR.PATCH` tag.

## What Changes

- Xray log rotation selects guarded recovery whenever the protected transport
  egress generation owns Xray. It uses the same predicate as transport egress
  preparation, not the optional toggle.
- The AmneziaWG role does not install `resolvconf`. Server configurations do
  not set `DNS=`, so `awg-quick` never calls it.
- The firewall drops forwarded AmneziaWG traffic to the canonical private and
  reserved recipient destinations before the uplink accept rule.
- The watchdog still reports and alerts on a failed configuration validation,
  but it withholds restart or recovery for that unit in the same run.
- The Hysteria role refuses a version that is not an exact stable
  `vMAJOR.MINOR.PATCH` tag before acquisition. This enforces the existing
  rule that pre-releases never reach production; it is not a contract break.

## Capabilities

### New Capabilities

- `ansible/deployment-readiness-runtime`: rotation recovery authority,
  AmneziaWG host resolver and destination boundaries, watchdog recovery
  withholding after failed validation, and stable Hysteria pins.

### Modified Capabilities

- None. Existing transport, firewall and watchdog contracts remain in force.

## Impact

- Ansible roles: `monitoring`, `amneziawg`, `firewall`, `watchdog`,
  `hysteria`, their role notes, template snapshots and unit regressions.
- No Terraform, secrets schema, vpnd, client payload or listener change.
- A deployed node changes on its next converge only. This change authorizes
  no deployment.
