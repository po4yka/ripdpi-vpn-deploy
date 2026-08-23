## Context

Seven findings share a theme: implementation drifted from the repo's own written conventions (hardening skill floors, no-root-cron rule, pinning discipline, rate-limit layering). The dns-morph exposure is the only outright defect; the rest are convention-vs-code reconciliations. Related context: ANS-1787463116251274 already leveled internet-facing transport units; the two zero-hardening inline units here are the remaining gap.

## Goals / Non-Goals

- Goal: make shipped behavior match every stated security convention, or amend the convention deliberately where reality is preferred.
- Non-goal: introducing new controls beyond the stated floors (no new geo-blocking, no new IDS surfaces).

## Decisions

- dns-morph: task flags only; rotation of the key itself is an operator action outside this change (documented in the task note).
- Inline units become templates rather than drop-in overrides: single artifact, molecule-verifiable.
- ICMPv6: split required types explicitly instead of rate-limiting the family — breaking NDP would be worse than the current state.
- Timer migration removes the cron file in the same converge to prevent double-scheduling.
- WARP pin: prefer shipping a real default digest; fail-closed fallback if upstream rotation invalidates it.
- Rate-limit layering: decide before implementation in review; both sides are implementable, the design constraint is one-layer-only with documentation synced.

## Contracts and ownership

- Roles owned: dns-morph-bridge, backup, geodata, firewall, cdn-front, warp-outbound, subscription-host, nginx-xhttp.
- security-verify.yml gains assertions (ICMP limits); docs conventions may gain carve-out text.

## Risks / Trade-offs

- Over-tight sandboxes can break backup/restore flows → mitigate via ReadWritePaths iteration plus systemd-analyze verify and one real run each in molecule.
- Strict CSP on recipient pages could break inline styles → tune to static-page needs and test against vpnd-generated share bundles.
- Mandatory WARP pin fails deploys after legitimate upstream rotation → failure message documents the update procedure.

## Migration Plan

- Forward: converge applies templates/timers/rules atomically per role.
- Rollback: revert role commits; cron file removal is re-installable by revert.
- Gates: molecule per touched role, check-mode security-verify, `make ci-fast`, `make validate`.
