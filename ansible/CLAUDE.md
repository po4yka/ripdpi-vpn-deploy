# ansible — runtime state ownership

## Design decisions

**One playbook per intent** — `site.yml` (deploy), `verify.yml`, `security-verify.yml`, `smoke-test.yml`, `rollback-config.yml`, `rollback-xray.yml`, `rotate-credentials.yml`. No mega-playbook with conditional flags; new intent = new playbook.

**Roles are feature-toggleable** — `group_vars/all.yml` carries `vpn.enable_*`
booleans. Disabling a profile is a config change, not a code change.

**Per-role `defaults/main.yml`** — every variable a role consumes has a
default. `group_vars` only overrides. Reading a role's defaults file tells
you everything it exposes.

**Inventory is rendered, not committed** — `scripts/render-inventory.sh`
reads `terraform output -json` and emits `inventory/<env>.yml`. Don't edit
the rendered file.

**Listener collisions fail before convergence** — `site.yml` renders a sanitized public listener manifest and runs `scripts/check-listener-collisions.py` in pre_tasks before any role mutates services or nftables.

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
- **Role ordering matters** — baseline → package_updates → firewall → intrusion_prevention → geodata → (xray, nginx-xhttp, hysteria, amneziawg) → monitoring → backup → watchdog.
  `site.yml` enforces this; don't rely on `meta: dependencies`.
- **Handler queues fire at end-of-play** — a service restart triggered in
  role A doesn't happen until role B is done. Use `meta: flush_handlers` if
  later roles depend on the restart having happened.
