## Purpose

Define the kernel, account, package and journal-budget properties that every managed VPN node must hold after baseline convergence, so that a recreated node does not return to distribution or provider defaults.

## ADDED Requirements

### Requirement: REQ-BASELINE-KERNEL-GAPS — Redirect, kexec and BPF JIT policy

The baseline sysctl policy MUST set `net.ipv6.conf.all.accept_redirects` and `net.ipv6.conf.default.accept_redirects` to `0`, `kernel.kexec_load_disabled` to `1`, and `net.core.bpf_jit_harden` to `2`. These keys MUST be mandatory: a host that cannot apply one of them MUST fail convergence. The BPF JIT key MUST be rendered only where the kernel exposes the control, which excludes a container network namespace.

#### Scenario: Converged node holds the kernel policy

- **WHEN** the baseline role converges a managed node
- **THEN** the persistent policy file contains the four keys with the stated values and the running kernel reports the same values

#### Scenario: Unavailable hardening key is not ignored

- **WHEN** the kernel refuses one of the four keys
- **THEN** the sysctl reconciliation reports a mandatory failure and convergence stops

### Requirement: REQ-BASELINE-ROOT-LOCK — Root password is locked

The baseline role MUST leave the root account with a locked password. It MUST NOT change the deployment account or its authorized keys.

#### Scenario: Provider-set root password

- **WHEN** a node arrives with a usable root password hash
- **THEN** after convergence the root password status is locked and the deployment account still authenticates with its key

### Requirement: REQ-BASELINE-UNUSED-PACKAGES — Unused distribution services are absent

The baseline role MUST purge `modemmanager`, `apport`, `open-vm-tools` and `snapd`. Packages that the storage or provider lifecycle can depend on (`open-iscsi`, `multipath-tools`, `acpid`, provider guest agents) MUST stay untouched.

#### Scenario: Stock cloud image

- **WHEN** a node built from a stock cloud image converges
- **THEN** the four packages are not installed and convergence is idempotent on the second run

### Requirement: REQ-JOURNAL-BUDGET — Journal budget holds the stated retention

The journald policy MUST set a 1G size budget and keep the 14-day retention limit and persistent storage.

#### Scenario: Monitoring enabled

- **WHEN** the monitoring role renders the journald policy
- **THEN** the policy file states `SystemMaxUse=1G` and `MaxRetentionSec=14day`
