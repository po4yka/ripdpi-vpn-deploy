# Change: Complete Ansible role audit improvement contracts

Task ID: `ANS-1791586652330612`

## Why

The remaining role audit opportunities allow unbounded recipient history,
interrupted activation, shared TLS staging, shared Naive credentials, missed
log inputs/recovery notifications, inaccurate counts and unverifiable audit
acceptance. Implement I07-I15 and the remaining WARP fixture defect F43 in
existing PR 282, retaining the P1/P2 fixes and the bounded I01-I06 evidence.

## What Changes

- Bound bootstrap audit history and compact consumed markers behind durable
  retirement authority; restored generations cannot resurrect retired grants.
- Persist desired-versus-activated state and reconcile interrupted publication;
  eliminate shared self-steal TLS staging/publication races.
- **BREAKING:** replace the global Naive credential pair with per-device clients
  and explicit issuance/revocation; update every consumer and synthetic fixture.
- **BREAKING:** bootstrap-only tokens carry issuance time and expire independently
  of restored payload metadata; legacy bootstrap tokens are refused. Ordinary
  subscription tokens retain their existing contract.
- Recover policy tailing from copytruncate; count all observed honeypot events
  independently of bounded logs; validate and share private scrape endpoints.
- Retry persisted recovery notification intent independently of healthy state.
- Make opt-in audit acceptance require actual fresh successful collection while
  keeping default reporting non-blocking; make WARP role recovery tests real.

## Capabilities

### New Capabilities

- `operations/ansible-role-audit-improvements`: bounded recipient lifecycle,
  durable activation/notification intent, per-device Naive access and explicit
  metric/audit acceptance.

### Modified Capabilities

- None; previous role remediation requirements remain in force.

## Impact

- Ansible role tasks, templates, units, local helpers and lifecycle tests.
- Secret schema/examples, issuance/revocation scripts and direct consumers.
- Shared private-listener/activation interfaces, reviewed snapshots and CI.
- Source-only validation and PR publication; no provider, fleet, credential
  issuance/decryption, live deployment, external client or human acceptance.
- No new production dependency, compatibility shim or P1/P2 safety relaxation.

## PR review remediation

Address the current inline review and all open CodeQL findings in PR 282: failure-safe descriptor ownership, owner-only runtime logs/state, explicit supported TLS floors, file-type-aware template rendering, unused code removal and private selected-device export. Preserve existing safety and positive protocol behavior.
