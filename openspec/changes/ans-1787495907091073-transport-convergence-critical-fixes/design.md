## Context

Ten defects from the cloud-init → Ansible audit (2026-08-23) each break convergence or silently weaken a shipped control; evidence and file:line citations live in the linked portfolio record and the audit report. All ten are local to role task/template/handler files; none change listener contracts, toggles, or secrets schemas.

## Goals / Non-Goals

- Goal: restore correct convergence and honest control behavior for the ten scoped defects with minimal, per-role diffs.
- Non-goal: pattern consolidation (shared install/lifecycle helpers), new hardening floors, listener or contract changes — those live in sibling changes.

## Decisions

- wg-quick hooks: join the PostUp value into a single physical line (rejected: repeated PostUp directives — valid but harder to diff and review).
- WARP gate: one conjunctive boolean expression (rejected: keeping the list — Ansible ANDs list items, which is the bug).
- hysteria-realm access: append-only supplementary group on the existing user task (rejected: SupplementaryGroups in the unit — the user task is the single identity surface).
- Mirror state: rsync excludes in the pull script (rejected: relocating files — the revoked path is already referenced by the Python service defaults and molecule fixtures).
- AWG handler: restart (rejected: conditional reload-then-start — two verbs for one lifecycle, and reload cannot apply address/route changes).
- UFW probe: `check_mode: false` on the status command, matching the adjacent `sshd -T` probe.
- Honeypot: absolute monotonic deadline per connection (rejected: per-recv timeout increase — does not bound total hold time).

## Contracts and ownership

- Roles owned by this change: split-hop-egress, warp-outbound, hysteria-realm, subscription-host, amneziawg, firewall, hysteria, honeypot (tasks/, templates/, handlers/, molecule/).
- No Terraform, vpnd, secrets-schema, or listener-contract surface changes.

## Risks / Trade-offs

- AWG restart drops active tunnels briefly on peer changes → acceptable for this role's convergence model; documented in the role doc.
- Stricter WARP gate can fail hosts that previously converged silently broken → intended fail-loud behavior.
- Honeypot deadline may terminate legitimately slow scanners earlier → detection value unaffected; slot availability improves.

## Migration Plan

- Forward: single converge applies all ten fixes; no state migration.
- Rollback: revert the role commits; rendered configs regenerate on next converge.
- Gates: per-role molecule scenarios, then `make ci-fast`, `make validate` before merge.

## Reusable steps
