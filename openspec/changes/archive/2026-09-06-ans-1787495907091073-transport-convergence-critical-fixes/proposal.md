# Change: Fix production-breaking transport convergence defects

Task ID: `ANS-1787495907091073`

## Why

The cloud-init → Ansible audit found ten defects that break convergence or silently weaken a shipped control on real nodes: the split-hop egress leg cannot pass wg-quick parsing at bring-up, the WARP egress health gate accepts a disconnected tunnel, hysteria-realm crash-loops when it shares TLS material with hysteria, the subscription mirror deletes its own revocation state and pinned host keys on every pull, AWG instance updates fail or half-apply through a reload handler, the firewall role aborts check-mode runs on UFW-preinstalled images, uppercase revocation hashes never match, Hysteria config scalars render unquoted YAML, the amneziawg unit declares a target that does not exist, and honeypot worker slots can be held forever by slow readers. Each defect either fails a deploy outright or passes one while shipping a degraded control.

## What Changes

- `split-hop-egress.conf.j2` renders PostUp directives as wg-quick-parseable single lines (or repeated PostUp directives) instead of backslash-continued multiline shell.
- The warp-outbound trace gate fails unless curl succeeds AND the trace reports an active tunnel.
- hysteria-realm gains read access to shared hysteria TLS material (supplementary group or equivalent).
- The subscription mirror pull excludes the revoked-hashes file and `.ssh/` state from reconciliation.
- The amneziawg config-change handler restarts instances (safe for inactive units, applies full up-time state) instead of reloading a oneshot unit.
- The firewall role reads UFW status with `check_mode: false` so dry-runs complete on UFW-preinstalled hosts.
- Revocation hash comparison normalizes case on ingest or match.
- Hysteria template interpolations emit quoted (JSON-encoded) YAML scalars.
- `awg-quick.target` is either shipped or the dangling `PartOf=` reference is removed.
- The honeypot enforces a total per-connection deadline instead of a per-recv timeout.

None of these change listener contracts, ports, toggles, or secrets schemas.

## Capabilities

### New Capabilities

- `ansible/transport-convergence`: Observable correctness contract for transport and defensive-service convergence: parseable WireGuard hook configuration, health-gated egress activation, readable shared TLS material, self-consistent mirror pulls, restart-safe AWG lifecycle, check-mode-safe firewall tasks, normalized revocation matching, well-formed rendered configs, resolvable unit dependencies, and bounded connection handling.

### Modified Capabilities

- None

## Impact

- Ansible roles: split-hop-egress, warp-outbound, hysteria-realm, subscription-host, amneziawg, firewall, hysteria, honeypot.
- Molecule scenarios for the touched roles gain assertions where stubbing previously masked the defect (split-hop hook shape, mirror pull preservation).
- No Terraform, vpnd, secrets-schema, or listener-contract changes.
