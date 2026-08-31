# ANS-1787497148207353: Consolidate duplicated runtime patterns across roles

## Objective

One shared implementation exists for each duplicated runtime concern, consumers migrate onto it without behavior change beyond the documented capability gains (rollback symlinks, validators, liveness waits), and scaffold/restore-layout hazards become fail-closed assertions.

## Ownership

- The primary agent owns the new `ansible/roles/runtime-release` role and its `runtime_release_*` API, migration commits for the six release consumers named by `REQ-INSTALL-RELEASE-SHARED` and the two migration steps, ansible/templates/listener-manifest.json.j2, group_vars/all.yml defaults section, and per-role molecule updates. Other roles in proposal.md Impact participate only in their corresponding concerns.
- Serialized shared-file lane: group_vars/all.yml and listener-manifest.json.j2 are edited exclusively within this change; SEC-1787496747898735 owns backup/geodata units and is not touched here.

## Execution

- [x] ANS-1787496118906923 Introduce the shared runtime-release role: stat-guarded checksum download, releases/<version> directory, current symlink, /usr/local/bin link, single arch-slug derivation; unit tests pin its `runtime_release_*` contract #chore !high @item:ANS-1787497148207353
- [ ] ANS-1787496118907057 Migrate xray-runtime, hysteria, hysteria-realm, snell onto runtime-release preserving their existing pins and molecule outcomes #chore !high @item:ANS-1787497148207353 @blocked_by:ANS-1787496118906923
- [ ] ANS-1787496118906866 Migrate probe-matrix-target and dns-morph-bridge onto runtime-release granting them release-dir + rollback symlink for the first time #chore !low @item:ANS-1787497148207353 @blocked_by:ANS-1787496118906923
- [x] ANS-1787496118907179 Collapse the amneziawg dual source-build blocks into one loop over project descriptors with shared receipt handling; naive/xray-runtime source-build idioms adopt the same receipt helper #chore !low @item:ANS-1787497148207353
- [ ] ANS-1787496118907152 Bring probe-matrix-xray/probe-matrix-mtg plus the Ansible-owned real-vps server-awg, echo and two mode-specific firewall services to the sandbox floor with molecule runs per template #chore !low @item:ANS-1787497148207353
- [ ] ANS-1787496118907351 Add template validators for hysteria (sing-box check), hysteria-realm (sing-box check), naive (caddy validate), dns-morph-bridge (yaml parse) and post-restart liveness waits for restart-only service handlers matching the xray listen pattern #chore !high @item:ANS-1787497148207353
- [ ] ANS-1787496118907135 Single-source listener port defaults in group_vars/all.yml; strip literal default() duplicates from roles and listener-manifest.json.j2 so the manifest renders from declared defaults only; express cohort-vs-single-port branching once #chore !high @item:ANS-1787497148207353
- [ ] ANS-1787496118907278 Move split-hop-egress NAT rules into a standalone validated policy file loaded by a dedicated loader task, removing inline shell from wg-quick hooks #chore !low @item:ANS-1787497148207353
- [ ] ANS-1787496118906586 Retire hand-written collision asserts (hysteria-realm vs subscription, naive mutual exclusion) after adding checker coverage proof for those pairs; keep a pointer comment #chore !low @item:ANS-1787497148207353
- [ ] ANS-1787496118907125 Emit the P0 shape contract (flow_mode/finalmask branches) from one shared template consumed by both xray config.json.j2 and watchdog reality-probe.json.j2 #chore !low @item:ANS-1787497148207353
- [ ] ANS-1787496118907037 Make cascade-ingress activation-safe as rendered: pair 0.0.0.0/0 AllowedIPs with Table = off plus documented mark-based routing intent, or pin a non-default-route default; give cascade-egress an explicit forward-contract preflight or document forwarding out of scaffold scope #bug !low @item:ANS-1787497148207353
- [ ] ANS-1787496118907217 Assert restic-backend mirror restore layout: after restore, $DEST contains sub/ at root or the script fails loudly naming the snapshot-path mismatch #bug !low @item:ANS-1787497148207353
- [ ] ANS-1787496118906414 Run staged gates per migration commit: each consumer's molecule scenario before and after switch-over, then full make ci-fast and make validate on the final state #test !high @item:ANS-1787497148207353 @blocked_by:ANS-1787496118906923 @blocked_by:ANS-1787496118907057 @blocked_by:ANS-1787496118906866 @blocked_by:ANS-1787496118907179 @blocked_by:ANS-1787496118907152 @blocked_by:ANS-1787496118907351 @blocked_by:ANS-1787496118907135 @blocked_by:ANS-1787496118907278 @blocked_by:ANS-1787496118906586 @blocked_by:ANS-1787496118907125 @blocked_by:ANS-1787496118907037 @blocked_by:ANS-1787496118907217

## Verification

Use the exact gates and evidence categories in `verification.md`.
