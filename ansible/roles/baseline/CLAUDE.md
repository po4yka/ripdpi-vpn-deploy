# role: baseline — every host starts here

## Design decisions

**Explicit restricted account admission** — `baseline_ssh_extra_allowed_users` adds reviewed accounts to AllowUsers through the recoverable controller. The intent has only the exact six-option Match User restriction grammar. The guest planner places this suffix at the end of sshd_config, leaving the include fragment global-only; OpenSSH Match all does not restore global directive context. Native context output must prove all restrictions. Arbitrary Match blocks remain rejected.


**Resolver transitions preserve DNS first** — ordinary profiles retain the resolved stub. DNS-Morph migrates only known stub symlinks to a verified upstream resolver before disabling the stub; custom stub files or absent upstreams fail before mutation. The restart happens before dependent listeners converge.

**Forwarding has one owner** — `tasks/forwarding.yml` removes the retired split-hop fragment and publishes priority-91 IPv4 forwarding for AWG or split-hop egress, with IPv6 only for AWG. Direct split-hop convergence reuses this entry point and explicitly passes `baseline_forwarding_split_hop_egress_active`; an active role requires forwarding even when the site-selection toggle is false. Without an active caller or enabled routing profile, baseline removes the override.

For SSH recovery helper or unit changes, inspect the [bundle and controller consumers](../../../scripts/DESIGN-NOTES.md#ssh-recovery--install-sshd-recoverypy-make-install-ssh-recovery).

**Sets ground state, not policy** — installs sysctl baseline, time sync
(`systemd-timesyncd`), OpenSSH prerequisites, and IP-forwarding sysctl for enabled AWG and split-hop egress workloads. The controller-owned second site play publishes SSH
policy only after the VPN stack converges. Doesn't open ports or install
Xray/nginx; other roles layer on top.

**No reboots from this role** — reboots belong to `playbooks/os-maintenance.yml`,
which checks `/var/run/reboot-required` and reboots one host at a time.
A reboot mid-deploy would burn idempotency.

**SSH policy lives in `security_controls`** — the role still owns the drop-in,
but operator posture knobs live under `security_controls.ssh_*`, not `vpn.*`.

**One SSH transaction timeout ceiling** — the installed request adapter uses
the transaction engine's maximum. The controller's promotion proof budget can
consume that full interval; a narrower adapter bound refuses otherwise valid
check-mode and deploy requests before the engine sees them.

**Baseline failure diagnostics stay controller-private** — deploy passes one
fresh persistent receipt path and its frozen parent identity through the
private transaction variables. The localhost controller validates them before
SSH and writes only an allowlisted
category after a handled failure; this role keeps the command `no_log` and
never registers, renders, or debugs receipt contents. Check mode passes null,
success writes nothing, and the receipt cannot authorize confirmation.

**No host-firmware daemon on VPS guests** — cloud nodes cannot flash their
hypervisor firmware. Baseline removes `fwupd` instead of leaving an irrelevant
daemon able to degrade systemd after a partial package update.

**Legacy SSH ownership migration is a separate transaction** — the opt-in
recovery installer does not import baseline or edit SSH configuration. Its
planner preserves full effective policy for known 10/20/50 layouts; the durable
helper restores unconfirmed changes. Never use a full baseline converge as
ownership-only migration. On a fresh Debian node, run the explicit
`migrate-ssh-ownership` controller after dual-path bootstrap and before the
first ordinary dry-run. It requires strict public and Tailnet SSH/SFTP proof
and the installed recovery generation. Local tests are not staging acceptance.

**Optional BBR cannot mask mandatory hardening failures** — only the congestion
control key uses the per-setting optional prefix. The ordered helper retains
the standard directory/file precedence and applies marked optional settings
separately because the supported procps release still returns a failing status
for them. Every mandatory segment retains its normal nonzero failure, including
when optional BBR and a mandatory setting fail together.

## What's done well

- **Sysctl convergence self-heals after interrupted plays** — the role reapplies `/etc/sysctl.d` on every converge, so a play that failed after writing a file but before handlers ran cannot leave runtime values stale indefinitely.

- **Single source for sysctl** — `templates/sysctl-vpn.conf.j2` consolidates
  kernel tunables (`net.ipv4.tcp_fastopen`, `tcp_bbr`, UDP buffer sizes, etc).
  Loaded at priority 90 so cloud-init defaults can't override.
- **Forwarding is isolated from hardening** — `90-vpn.conf` keeps forwarding
  disabled; `91-vpn-forward.conf` is the only place that enables IPv4/IPv6
  forwarding for AWG and IPv4 forwarding for split-hop egress.
- **Time sync via `systemd-timesyncd`** — installed and enabled. REALITY breaks
  if clocks drift > 90 s; `verify.yml` asserts sync state.
- **SSH hardening via a recoverable transaction** —
  `templates/sshd_config.d-hardening.conf.j2` is rendered by Ansible, while the
  exact-node controller publishes it with durable rollback and fresh transport
  proof after the VPN stack converges.
- **SSH algorithms are pinned as runtime policy** — the controller accepts only
  provider defaults or the exact managed Ciphers, MACs, and KexAlgorithms
  allowlists, validating global and requested contextual effective policy.
- **SFTP is internal and managed once** — the packaged `Subsystem sftp` line is
  commented before the drop-in declares `internal-sftp`, avoiding duplicate
  Subsystem directives on Debian/Ubuntu while preserving Ansible file transfer.
- **Moduli pruning is optional and idempotent** — when
  `security_controls.ssh_prune_moduli` is true, `/etc/ssh/moduli` is pruned to
  groups with field 5 >= 3071, with `/etc/ssh/moduli.prev` as local backup.
- **IP forwarding is conditional** — enabled for AWG or split-hop egress; the override is removed when both are disabled. Avoids forwarding on P0-only nodes.

## Pitfalls

- **Shadowed root-login declarations need policy proof** — ownership migration
  may comment one main `PermitRootLogin yes` after the canonical Include only
  with bootstrap root denial and real global/contextual `permitrootlogin no`.
  Never accept an unshadowed line or edit it directly on the host.

- **Activation must not invalidate its own recovery proof** — run one fresh
  recovery execution outside the transaction lock, then fence its result after
  reacquiring the lock. Cached success or busy status alone is never readiness.
- **Readiness can overlap periodic recovery** — wait within the existing
  30-second budget for the observed invocation to complete successfully.
  Invocation, generation, and boot changes refuse; never start or restart
  a worker to replace a failed result.
  Apply activation observes an in-flight worker before requesting its one
  fresh execution. Waiting and fresh proof share the same deadline; only
  completed success or the existing exit-75 contention category permits that
  request, and the requested execution must still finish with exit zero.
- **Does not install `chrony` or `unattended-upgrades`** — time sync is
  `systemd-timesyncd` (distro default on Debian 13/Ubuntu 24.04). Unattended
  upgrades are not configured by this role; operators add them separately.
- **DNS-Morph needs port 53** — only this optional workload disables the resolved stub after its resolver migration has passed; ordinary hosts retain the stub.
- **Fresh Debian check mode has no timesync unit yet** — apt plans its
  installation, but cannot create the unit during a dry run. Require that
  package change before deferring service activation; real convergence always
  starts and enables the service.
- **Cloud-init still creates the admin user first** — baseline hardens sshd
  after the first connection succeeds. Don't remove the cloud-init admin-user
  path unless another first-boot access path replaces it.
- **`RequiredRSASize` is opt-in** — default `security_controls.ssh_required_rsa_size`
  is `0` so older OpenSSH versions never see an unsupported directive.
- **Hostname change requires re-running cloud-init handlers** — don't
  change `ansible_hostname` mid-deploy.
- **Firmware belongs to the provider** — do not reinstall `fwupd` on these VPS
  nodes to silence a failed unit; remove it and clear the obsolete failure.
