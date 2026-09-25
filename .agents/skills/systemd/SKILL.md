---
name: systemd
description: Conventions for the systemd units and timers that Ansible roles render (hardening floor, capabilities, secret delivery, timers, verification). Use when adding or changing a *.service.j2 or *.timer.j2 template or a static *.service or *.timer file under ansible/roles/, or the tasks and handlers that install and restart one.
---

# systemd units (vpn-deploy)

Most runtime services are units rendered from `ansible/roles/<role>/templates/*.service.j2` (and `*.timer.j2`) into `/etc/systemd/system/`. Six security-sensitive recovery units are static files installed as-is: the SSH recovery units in `ansible/roles/baseline/templates/` (`vpn-sshd-*`) and the Tailnet firewall recovery units in `ansible/roles/firewall/files/` (`vpn-tailnet-network-*`); the same rules apply to them. List every unit with `git ls-files 'ansible/roles/**' | rg '\.(service|timer)(\.j2)?$'`. Unit names do not always match role names: `awg-quick@<iface>` (amneziawg), `caddy-naive` (naive), `vpn-watchdog` (watchdog), `vpn-backup` and `vpn-backup-restore-drill` (backup). Role-specific lifecycle pitfalls live in each role's `CLAUDE.md`.

## Authoring a unit

- Start from the full hardening floor used by `ansible/roles/xray/templates/xray.service.j2` and the other transport daemons: `NoNewPrivileges`, `PrivateTmp`, `ProtectHome`, `ProtectSystem=strict`, `ProtectKernelTunables`, `ProtectKernelModules`, `ProtectControlGroups`, `RestrictNamespaces`, `LockPersonality`, `RestrictRealtime`, `RestrictSUIDSGID`, `SystemCallArchitectures=native`, plus explicit `ReadWritePaths=` for the directories the service writes. About half of the existing units carry all twelve; when a service genuinely needs a directive relaxed, leave it out with a comment saying why rather than loosening the others.
- Grant capabilities narrowly: `CapabilityBoundingSet=` + `AmbientCapabilities=CAP_NET_BIND_SERVICE` for listeners on privileged ports, `CAP_NET_ADMIN` for AmneziaWG. Long-running daemons run as a dedicated `User=`; root units are limited to jobs that manage the host itself (interfaces, nftables, backups, watchdog restarts).
- Deliver secrets with `LoadCredential=<name>:<path>` and read them from `$CREDENTIALS_DIRECTORY` (the observability roles are the reference). Never put secret values on `ExecStart`/`ExecStartPre` command lines or in `Environment=`.
- `DynamicUser=` only for stateless helpers (e.g. `observability-telegram-relay`); a service that owns persistent state gets a real user and directory.
- Timers set `Persistent=true` whenever a missed run matters (13 of 15 existing timers do).
- Prefer a role-owned unit over a drop-in for a distro unit. The existing drop-ins (`sshd_config.d`, the real-VPS nftables drop-in) are config fragments, not unit overrides; nginx runs its stock unit.

## Lifecycle and verification

- Install with `ansible.builtin.template` (or `ansible.builtin.copy` for a static unit), then `daemon_reload` before enabling or restarting. Validation lives in tasks, not handlers, and must run before anything loads the new config: Xray validates through the template's `validate:` (`xray run -test`); nftables validates through `validate: "nft -c -f %s"` and is loaded by the explicit `Reload nftables before dependent roles run` task (firewall has no handler); nginx-xhttp runs an explicit `nginx -t` task and then `flush_handlers` to trigger its reload-only handler. Keep that validate-then-apply order when adding a service with a config test.
- Check the rendered unit with `make snapshot-check` (golden files under `tests/snapshot/golden/<role>/templates/`) and converge it with `make molecule-test ROLE=<role>`. Only `backup` and `geodata` currently run `systemd-analyze verify` in their Molecule `verify.yml`; add it when you introduce a new unit. Molecule verifies otherwise assert `systemctl is-active` or unit presence.
