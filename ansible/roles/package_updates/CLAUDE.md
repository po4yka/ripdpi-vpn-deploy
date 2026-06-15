# role: package_updates — safe unattended security updates

## Design decisions

**Security updates only by default** — config allows Debian/Ubuntu security
origins and leaves broader updates off unless `package_updates.security_only`
is false.

**No automatic reboot by default** — `package_updates.automatic_reboot`
defaults false. Reboots stay operator-controlled so deploys do not silently
interrupt active tunnels.

**Opt-in at site level** — `site.yml` runs the role only when
`security_controls.unattended_upgrades` is true. Role defaults are safe, but
the fleet default remains disabled.

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
