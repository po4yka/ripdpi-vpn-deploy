# ANS-1787463116251274: Align systemd hardening across internet-facing transports

## Objective

Internet-facing transport units carry a uniform, strong systemd sandbox:
`hysteria` gains the MemoryDenyWriteExecute + SystemCallFilter pair already
present on `hysteria-realm`, and `snell` (research tier, internet-facing)
gains the kernel-surface protections (`ProtectKernelTunables`, `ProtectKernelModules`,
`ProtectControlGroups`, `RestrictNamespaces`) plus the same filter set.

## Ownership

- The primary agent owns
  `ansible/roles/hysteria/templates/hysteria-server.service.j2`,
  `ansible/roles/snell/templates/snell.service.j2`,
  their molecule scenarios' expectations, and this change's artifacts.
- hysteria-realm's unit is already at the target baseline and is not modified.

## Execution

- [x] ANS-1787463325958892 Add MemoryDenyWriteExecute and the SystemCallFilter allowlist (with @privileged/@resources denials) to the hysteria server unit, matching hysteria-realm's sandbox #bug !high @item:ANS-1787463116251274
- [x] ANS-1787463325959076 Bring the snell unit to the same baseline: ProtectKernelTunables, ProtectKernelModules, ProtectControlGroups, RestrictNamespaces and the shared SystemCallFilter set; run the hysteria and snell molecule scenarios plus named local gates #bug !high @item:ANS-1787463116251274

## Verification

Use the exact gates and evidence categories in `verification.md`.
