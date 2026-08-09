# role: package_updates — safe unattended security updates

## Design decisions

**Security updates only by default** — config allows Debian/Ubuntu security
origins and leaves broader updates off unless `package_updates.security_only`
is false.

**No automatic reboot by default** — `package_updates.automatic_reboot`
defaults false. Reboots stay operator-controlled so deploys do not silently
interrupt active tunnels.

**Enabled for the fleet baseline** — `site.yml` runs the role when
`security_controls.unattended_upgrades` is true, and the fleet default enables
it. Profiles may disable it only when their lifecycle provides an equivalent
patching mechanism.

**Full upgrades are a separate rolling intent** — unattended runs remain
security-only. `playbooks/os-maintenance.yml` owns full upgrades and any
required operator-controlled reboot, one host at a time.

## What's done well

- **Validation before trust** — tasks run `unattended-upgrade -d --dry-run`
  after rendering apt config.
- **No mail server install** — reports target local `root`; the role installs
  `apt-listchanges` but does not add an MTA.
- **Apticron is explicit opt-in** — it is checked for availability and installed
  only when `package_updates.install_apticron` is true.

## Pitfalls

- **Do not manage Xray/Hysteria/AmneziaWG pins here** — binary version policy
  lives in role defaults, SOPS schema, and release-line docs.
- **Container dry-runs are weaker than real hosts** — Molecule verifies
  package/config shape; live nodes still need `make verify` after enabling.
- **Automatic reboots are a policy change** — keep them disabled unless an
  operator has a separate rollout and alerting plan.
- **Do not add full upgrades to convergence** — routine `site.yml` deploys must
  not turn an application change into an implicit OS upgrade or reboot.
