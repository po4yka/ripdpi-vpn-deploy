# Change: Consolidate duplicated runtime patterns across roles

Task ID: `ANS-1787497148207353`

## Why

The audit quantified structural duplication that makes every future change a multi-site lockstep edit and leaves silent capability gaps: six divergent fetch-verify-install implementations (rollback symlink exists on only four of six), the amneziawg build recipe copy-pasted ~90 lines inside its own tasks file plus two more source-build idioms elsewhere, systemd hardening spread across unit templates from 15 directives down to zero, validate-before-restart plus liveness-wait existing on only three service roles while four render configs with no validation at all, port defaults mirrored in roughly fourteen places across the listener manifest with cohort branching re-implemented three times, four different nftables table lifecycle idioms (one of which bypasses validate-before-load entirely), port-collision defense split between a global checker and hand-written per-role asserts, and the P0 packet-shape contract encoded in parallel by xray and watchdog. Separately, the cascade-ingress scaffold ships an AllowedIPs default that would hijack the default route if ever activated as rendered, and the restic mirror backend lacks any assertion that restored payloads land where the delivery service reads them.

## What Changes

- A shared `runtime-release` role with a `runtime_release_*` API provides one fetch-verify-install path (release dir, current symlink, arch-slug derivation); the six consumer roles migrate onto it.
- The amneziawg source-build block collapses to a loop over project descriptors;
  receipt handling becomes the single build-verification idiom. The shared
  helper owns a fixed private stage, bounded per-project serialization,
  all-output digest validation, compensating live publication, and receipt
  durability; Naive and Xray source consumers adopt the same transaction.
- Remaining unhardened Ansible-owned unit templates (the probe-matrix pair plus real-vps server, echo and mode-specific firewall services) reach the sandbox floor; the external sentinel and backup/geodata units remain with their existing owners.
- hysteria, hysteria-realm, naive, and dns-morph-bridge gain template validators; restart-only roles gain post-restart liveness waits matching the xray pattern.
- Port defaults become single-sourced in group_vars/all.yml; role defaults and the listener manifest reference them instead of duplicating literals; cohort branching is expressed once.
- nftables scoped-table lifecycles collapse onto the validated standalone-policy pattern; the split-hop egress PostUp embeds no shell rules.
- Per-role collision asserts retire after proving the global checker covers those pairs.
- The P0 shape contract is emitted from one shared source consumed by xray and watchdog.
- cascade-ingress scaffold pins non-default-route AllowedIPs or pairs 0.0.0.0/0 with Table=off plus documented policy-routing intent.
- The mirror script asserts the restored tree contains sub/ at DEST root for the restic backend.

## Capabilities

### New Capabilities

- `ansible/runtime-patterns`: Observable contract for shared release installation, single-idiom source builds, leveled unit hardening, uniform config-validation and liveness lifecycle, single-sourced listener defaults, one validated nftables policy idiom, checker-owned collision defense, single-sourced P0 shape contract, activation-safe scaffolds, and asserted mirror restore layout.

### Modified Capabilities

- None

## Impact

- Roles: xray-runtime, xray, nginx-xhttp, hysteria, hysteria-realm, snell, naive, dns-morph-bridge, probe-matrix-target, real-vps-awg-nat, warp-outbound (consumer migration), watchdog, subscription-host, split-hop-egress, cascade-ingress, firewall (manifest consumption).
- ansible/templates/listener-manifest.json.j2 and group_vars/all.yml (defaults become the single source).
- Migration is staged: shared installer first, then consumers one per commit, molecule gates per step.
