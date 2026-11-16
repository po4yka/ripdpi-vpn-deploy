## Context

The baseline role renders `/etc/sysctl.d/90-vpn.conf` from `sysctl-vpn.conf.j2` and applies it with `baseline_sysctl.py`, which treats every key without a leading `-` as mandatory. The same role already purges `fwupd` and `openipmi` and removes stock cloud-image accounts. The monitoring role writes a literal journald drop-in with `SystemMaxUse=500M` and `MaxRetentionSec=14day`. Live nodes showed 7 to 9 days of journal at the 500M limit and root filesystems at 27 to 38 percent of 20 to 25 GB.

## Goals / Non-Goals

- Goal: a recreated or redeployed VPN node holds the four properties in the spec without operator action.
- Non-goal: Tailscale update and pin policy, nginx sandboxing, observer host parity, auditd, the split-hop egress filter, and any live action (reboot, firewall source change, cleanup).

## Decisions

- Add the kernel keys to the existing template as mandatory keys. Rejected: optional (`-`) keys, because the role's rule is that hardening failures are fatal, and the three key families exist on the supported Ubuntu kernels.
- Render `net.core.bpf_jit_harden` only when `/proc/sys/net/core/bpf_jit_harden` exists, with the pattern the role uses for MPTCP: the control exists only in the initial network namespace, so a container cannot apply it, and a node always can. Set `net.core.bpf_jit_harden = 2`. Unprivileged BPF is already disabled, so level 1 adds nothing; level 2 also blinds constants for privileged programs at a small JIT cost.
- Lock root with the `user` module (`password_lock: true`) next to the stock-account tasks. Rejected: deleting the hash, which leaves an empty password field.
- Extend the existing purge task's package list. Rejected: masking units, which leaves the packages and their update surface installed. `open-iscsi` and `multipath-tools` stay because removal rebuilds the initramfs and the storage path differs by provider; `acpid` and guest agents stay because providers use them for shutdown and console functions.
- Raise the journal budget to 1G as a literal, matching the existing literal policy. Rejected: a new variable with no second consumer.

## Contracts and ownership

- `ansible/roles/baseline`: `templates/sysctl-vpn.conf.j2`, `tasks/main.yml`, Molecule `verify.yml`, role note.
- `ansible/roles/monitoring`: `tasks/enable.yml`, role note.
- `tests/snapshot/golden/baseline/templates/sysctl-vpn.conf.j2` and unit tests that render the sysctl template.
- No secrets, inventory, Terraform or `vpnd` contract changes.

## Risks / Trade-offs

- `kernel.kexec_load_disabled = 1` is one-way until reboot → no component uses kexec; `kexec-tools` is not installed on the live nodes. The key is not namespaced, so a privileged Molecule run also sets it on the container host until that host restarts.
- The purge removes the `ubuntu-server` metapackages → a simulated purge with autoremove on two live nodes removed only the four packages and their own dependencies.
- A kernel without one of the keys fails convergence → intended; Molecule and the dry run expose it before a live deployment.
- Purging `snapd` on a host with installed snaps would remove them → live nodes have no snaps; the dry run lists the removal.
- Locking root removes provider-console password login → the operating model recreates a node that has lost management access.
- A 1G journal uses up to 500M more disk → root filesystems have more than 12 GB free.

## Migration Plan

Forward: merge, then the normal dry run and deployment per node. The sysctl reconciliation applies the keys at once; journald restarts through the existing handler. Rollback: revert the commit and redeploy; the kexec key returns to `0` only after a reboot, and purged packages are not reinstalled by a revert. No compatibility break.
