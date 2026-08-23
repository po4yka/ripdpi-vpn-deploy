# Change: Establish single-owner sshd configuration layers

Task ID: `SEC-1787496881680472`

## Why

Two unmanaged-relative sshd drop-ins overlap: cloud-init writes `10-cloud-init-hardening.conf` (Port plus five hardening directives) and the baseline role writes `20-ansible-hardening.conf` repeating five of them. OpenSSH first-match-wins semantics mean the Ansible-managed layer cannot actually change any duplicated directive — a future edit deploys cleanly, passes validation, reloads, and silently does nothing. Fragment-isolated `sshd -t` validation cannot notice cross-file conflicts. Additionally neither layer pins Ciphers/MACs/KexAlgorithms, leaving algorithm negotiation to whatever each provider image ships.

## What Changes

- Directive ownership becomes single-owner by contract: the cloud-init drop-in keeps only boot-critical settings (Port, auth-off primitives); the managed baseline drop-in owns all tunable hardening directives.
- Both drop-ins carry ownership comments; a new baseline check fails when any directive appears in both files.
- The template task validates against the effective assembled configuration (post-write effective-config parse), not the fragment in isolation.
- The managed layer gains an explicit Ciphers/MACs/KexAlgorithms allowlist sized for the pinned images.
- verify.yml asserts the effective algorithm set alongside its existing effective-config checks.

## Capabilities

### New Capabilities

- `security/sshd-config-ownership`: Observable contract that every managed sshd directive has exactly one owning file per host, cross-file duplication fails convergence, validation covers the effective configuration, and algorithm negotiation is pinned and verified.

### Modified Capabilities

- None

## Impact

- terraform/shared/cloud-init.yaml.tftpl (drop-in reduced to boot-critical keys).
- ansible/roles/baseline (drop-in template, new duplicate-directive check, validation step).
- ansible/playbooks/verify.yml (effective-config assertions).
- Lockout risk is the main hazard; mitigated by keeping Port in the first-read file and by existing validate-before-reload discipline.
