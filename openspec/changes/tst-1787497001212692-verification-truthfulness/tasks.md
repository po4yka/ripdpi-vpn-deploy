# TST-1787497001212692: Make verification reflect deployed state

## Objective

Verification passes exactly when deployed state matches intent: subscription-only hosts have usable verify/smoke paths, drift checks compare full source identity, deployed listeners (primary and fallback) are asserted with their real ports, idempotence is tested where the contract declares it, scenario docs describe reality, and the single-SSH-listener guarantee is machine-checked.

## Ownership

- The primary agent owns ansible/playbooks/{verify,smoke-test,source-drift}.yml, ansible/molecule/{full-stack,full-stack-published}/, ansible/roles/{xray,amneziawg,reality-self-steal}/molecule/, docs/TESTING.md.
- Serialized shared-file lane: docs/TESTING.md is edited exclusively within this change.
- Step `TST-1787496118906595` is assigned to `codex/high-awg-role-molecule-20260828` for the default AWG scenario and adjacent tests only. Production role tasks and other steps retain their existing owners; the primary agent serializes board/counts and delivery.
- The same worktree owns the separate Xray step `TST-1787496118907291` after AWG: default converge/sequence and the existing idempotent-converge test file only; production roles and full-stack remain excluded.

## Execution

- [x] TST-1787496118906453 Add not vpn_subscription_only gating to the six unguarded transport assertion groups in verify.yml, mirroring sibling conditions #bug !high @item:TST-1787497001212692
- [x] TST-1787496118906712 Gate all transport blocks in smoke-test.yml for subscription-only hosts #bug !high @item:TST-1787497001212692
- [x] TST-1787496118906639 Extend the source-drift parity assert with deployed_source_manifest.source_revision == expected_source_revision #bug !high @item:TST-1787497001212692
- [x] TST-1787496118906882 Parameterize the verify.yml Hysteria check with hysteria_port | default(443) and add conditional TCP listener assertions for xray_fallback_port and nginx_xhttp_fallback_port when fallback_enabled #bug !high @item:TST-1787497001212692
- [x] TST-1787496118906321 Append an idempotence phase to full-stack and full-stack-published test sequences and make them pass (fix any revealed non-idempotent tasks) #bug !high @item:TST-1787497001212692
- [x] TST-1787496118907291 Add an idempotence phase to the xray molecule sequence and verify repeat converge preserves role-owned runtime symlinks with zero changes #bug !low @item:TST-1787497001212692
- [x] TST-1787496118906595 Rewrite the amneziawg converge to execute the role via include_role against synthetic local Git/build inputs and no-TUN tools, verifying role-owned outputs and idempotence #bug !high @item:TST-1787497001212692
- [x] TST-1787496118906567 Sync docs/TESTING.md rows with observed sequences (geodata/naive/warp-outbound syntax-only claims), add the missing reality-self-steal row, correct the amneziawg description #docs !low @item:TST-1787497001212692
- [x] TST-1787496118907256 Add a verify assertion that exactly one SSH listener exists per host (effective-config parse), guarding the socket/service reconciliation surface #bug !low @item:TST-1787497001212692
- [ ] TST-1787496118906996 Run named gates: touched molecule scenarios including both full-stack variants, make ci-fast, make validate, one live-inventory verify + source-drift cycle #test !high @item:TST-1787497001212692

## Verification

Use the exact gates and evidence categories in `verification.md`.
