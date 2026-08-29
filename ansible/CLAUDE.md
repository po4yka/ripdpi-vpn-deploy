# ansible — runtime state ownership

## Design decisions

**One playbook per intent** — `site.yml` (deploy), `os-maintenance.yml` (serial OS upgrades/reboots), `verify.yml`, `security-verify.yml`, `smoke-test.yml`, `rollback-config.yml`, `rollback-xray.yml`, `rotate-credentials.yml`. No mega-playbook with conditional flags; new intent = new playbook.
`install-sshd-recovery.yml` installs the isolated recovery foundation on one
explicit node; it never activates a migration or imports baseline handlers.

**Roles are feature-toggleable** — `group_vars/all.yml` carries `vpn.enable_*`
booleans. Disabling a profile is a config change, not a code change.

**Deployment profiles are explicit** — prefer `vpn-p0-minimal`,
`vpn-family-standard`, `vpn-device-full`, and `vpn-lab` group_vars for new
inventory cohorts. Legacy `vpn-p0`, `vpn-p1p2`, and `vpn-fullstack` remain
aliases for existing inventories and must stay guarded by `role-tiers.yml`.

**Per-role `defaults/main.yml`** — every variable a role consumes has a
default. `group_vars` only overrides. Reading a role's defaults file tells
you everything it exposes.

**Live source parity is explicit** — `node_manifest` records the clean source
revision and deployable digest. `source-drift.yml` compares both live values
with the current checkout; `deploy` and `verify` run that gate automatically.

**Injected fact aliases are disabled** — use `ansible_facts[...]` for gathered
facts. Top-level `ansible_*` names are reserved for magic and inventory vars.

**Technical cohort group names are preserved** — rendered inventory uses
hyphenated profile slugs. Ansible keeps those names verbatim without warning;
templates must address them with bracket notation rather than attribute syntax.

**Inventory is rendered, not committed** — `scripts/render-inventory.sh`
reads `terraform output -json` and emits `inventory/<env>.yml`. Don't edit
the rendered file.

**Listener collisions fail before convergence** — `site.yml` renders a sanitized public listener manifest and runs `scripts/check-listener-collisions.py` in pre_tasks before any role mutates services or nftables.

**Safety pre-tasks run under role tags** — secrets presence, SSH allowlist,
role-tier loading and approval guards use `always`, just like listener checks.
Selecting a transport tag must not bypass prerequisites for baseline/firewall.

**Provider listener contract is fail-closed** — inventory carries Terraform's resolved `public_listeners` contract. `site.yml` rejects any mismatch with the runtime manifest before roles run; the firewall role and `security-verify.yml` use that same contract rather than maintaining port lists.

**SSH listener verification uses effective state** — `security-verify.yml`
derives the single active port from `sshd -T` and passes it to the live
firewall verifier. `verify.yml` also reconciles that port with bounded
`ssh.service`/`ssh.socket` state; it never infers ownership from process scans.
Port 22 has no special-case exemption when sshd uses a custom listener.

**`molecule` for testing roles, full-stack for site.yml** — `molecule-test
ROLE=<name>` runs in a Docker container per role. `molecule-full-stack`
exercises `site.yml` end-to-end.

## What's done well

- **Idempotency is a contract** — every role's molecule scenario runs the
  play twice and asserts the second run is `changed=0`. Drift = bug.
- **No `command:` / `shell:` without `creates:` or `changed_when:`** —
  ansible-lint enforces this. Pre-commit + CI catch violations.
- **`fact_caching` in `ansible.cfg`** — speeds up re-runs without hiding
  changes (cache is per-host, invalidated on inventory change).
- **Vault is not used** — SOPS owns secrets. `VPN_SECRETS_FILE` env is
  loaded via `include_vars` at play start.

## Pitfalls

- **`become` defaults to root**, but the connection user is the non-root
  admin. Some tasks (geo block install, sysctl) need explicit `become_user`.
- **`changed_when:` on `command:` is mandatory** — otherwise it reports
  changed every run, breaking idempotency assertions.
- **`gather_facts: true` on every play** — needed for OS-specific branches.
  Don't disable globally; disable per-play if you must.
- **Gathered facts are not top-level variables** — `inject_facts_as_vars` is
  disabled for ansible-core 2.24 compatibility. Use `ansible_facts[...]`.
- **Hyphenated groups require bracket notation** — use `groups['vpn-p0-minimal']`,
  never `groups.vpn-p0-minimal`; `force_valid_group_names=ignore` intentionally
  preserves the inventory contract instead of silently replacing characters.
- **Role ordering matters** — baseline → package_updates → firewall → intrusion_prevention → geodata → transport/listener roles → monitoring → backup → watchdog → node_manifest.
  `site.yml` enforces this; don't rely on `meta: dependencies`.
- **OS maintenance is fleet-serial** — `os-maintenance.yml` upgrades and,
  when required, reboots one host at a time. It must reject residual packages
  and reboot markers before advancing.
- **Handler queues fire at end-of-play** — a service restart triggered in
  role A doesn't happen until role B is done. Use `meta: flush_handlers` if
  later roles depend on the restart having happened.

- **Smoke cleanup requires ownership** — atomically claim the private workdir, use unique per-run unit names, and stop only clients whose start returned success; failed claims or starts never authorize cleaning another invocation, and an unconfirmed start/stop retains the private claim to block unsafe retries.
