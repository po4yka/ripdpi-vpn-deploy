# Change: Close baseline hardening gaps from the live fleet audit

Task ID: `SEC-1794807596362904`

## Why

A read-only audit of the live fleet on 2026-11-16 compared running hosts with the baseline policy. Every managed VPN node accepted IPv6 redirects, allowed a new kernel image to be loaded at runtime, and ran the BPF JIT without hardening. One node kept a usable root password that the provider set at creation. All nodes ran distribution services that the stack never uses. The 500M journal budget held 7 to 9 days of logs although the policy states 14 days. None of these states is controlled by the repository, so a recreated node reproduces them.

## What Changes

- The baseline sysctl policy adds mandatory keys that refuse IPv6 redirects, disable kexec image loading and harden the BPF JIT for all users.
- The baseline role locks the root account password.
- The baseline role purges `modemmanager`, `apport`, `open-vm-tools` and `snapd` together with the existing hardware-management packages.
- The monitoring journald policy raises the size budget from 500M to 1G; the 14-day retention is unchanged.
- The monitoring role requests a journal flush after it writes the policy. On an image without `/var/log/journal`, a restarted journald otherwise keeps the journal in `/run`: three live hosts held between 35 minutes and 9 hours of history.

No breaking change to an operator interface, secret schema or client contract.

## Capabilities

### New Capabilities

- `security/baseline-host-hardening`: kernel, account, package and journal-budget properties that every managed VPN node must hold after convergence.

### Modified Capabilities

- None

## Impact

- Ansible roles `baseline` and `monitoring`; their Molecule scenarios, unit tests and template snapshots.
- Runtime effect on managed nodes at the next deployment: three sysctl values change, four packages are removed, the root password is locked, and journald restarts with a larger budget. `kernel.kexec_load_disabled` cannot be reverted without a reboot.
- No Terraform, cloud-init, secrets, `vpnd` or client change.
