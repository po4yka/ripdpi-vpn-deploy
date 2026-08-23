# ANS-1787495907091073: Fix production-breaking transport convergence defects

## Objective

Every scoped transport and defensive service converges correctly on a real node and under check mode: wg-quick parses the rendered egress config, WARP activation requires a verified tunnel, co-resident realm services can read their TLS material, the subscription mirror preserves its own state across pulls, AWG config changes apply atomically per instance, dry-runs survive UFW-preinstalled images, revocation matching is case-insensitive, rendered Hysteria YAML is always well-formed, declared unit dependencies resolve, and honeypot connections hold slots only for a bounded time.

## Ownership

- The primary agent owns the task/template/handler files of roles split-hop-egress, warp-outbound, hysteria-realm, subscription-host, amneziawg, firewall, hysteria, and honeypot, plus their molecule scenarios.
- Serialized shared-file lane: none; each role directory is owned exclusively by this change.

## Execution

- [ ] ANS-1787496118906264 Join the split-hop-egress PostUp value into wg-quick-parseable form (single line or repeated PostUp directives); add a molecule assertion that no rendered config line ends in a lone backslash #bug !high @item:ANS-1787495907091073
- [ ] ANS-1787496118906728 Replace the warp-outbound trace failed_when list with a single conjunctive boolean so curl success plus an inactive tunnel fails the gate; extend the molecule/warp scenario expectation accordingly #bug !high @item:ANS-1787495907091073
- [ ] ANS-1787496118906155 Grant the hysteria-realm service user read access to shared hysteria TLS material (append-only supplementary group on the user task or SupplementaryGroups in the unit) when share_hysteria_tls is true; cover the shared-TLS path with real permissions in molecule #bug !high @item:ANS-1787495907091073
- [ ] ANS-1787496118906173 Add rsync excludes for the revoked-hashes file and .ssh state to vpn-sub-mirror.sh.j2 (or relocate both outside DEST like the credentials); extend molecule verify to assert both survive a triggered pull #bug !high @item:ANS-1787495907091073
- [ ] ANS-1787496118906083 Switch the amneziawg config-change handler from reloaded to restarted so inactive instances do not abort handler flush and full up-time state applies; note the brief tunnel drop in the release notes section of the role doc #bug !high @item:ANS-1787495907091073
- [ ] ANS-1787496118906658 Add check_mode: false to the firewall UFW status probe so make dry-run completes on hosts with preinstalled UFW; keep the disable step gated on the registered status #bug !high @item:ANS-1787495907091073
- [ ] ANS-1787496118906250 Normalize revocation hashes: lowercase entries when rendering the revoked file and strip/lower on match in vpn-bootstrap; add an uppercase-input test case #bug !high @item:ANS-1787495907091073
- [ ] ANS-1787496118906948 Quote interpolated string scalars in hysteria/templates/config.yaml.j2 via to_json (masquerade url, client name keys) matching the xray template discipline #bug !low @item:ANS-1787495907091073
- [ ] ANS-1787496118906870 Resolve the dangling awg-quick.target reference: ship a minimal target unit templated with Wants= for enabled instances, or remove the PartOf= line; assert the choice in molecule #bug !low @item:ANS-1787495907091073
- [ ] ANS-1787496118906549 Enforce a total per-connection deadline in honeypot.py.j2 computed from accept time (monotonic clock) replacing the per-recv timeout reset; count slot-exhaustion drops #bug !low @item:ANS-1787495907091073
- [ ] ANS-1787496118906757 Run named gates for all touched roles: molecule scenarios for split-hop-egress, warp-outbound, hysteria-realm, subscription-host, amneziawg, firewall, hysteria, honeypot; then make ci-fast and make validate #test !high @item:ANS-1787495907091073

## Verification

Use the exact gates and evidence categories in `verification.md`.
