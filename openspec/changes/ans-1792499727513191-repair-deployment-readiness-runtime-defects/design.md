## Context

See proposal.md for the audit findings. The deploy controller and Ansible
replace the canonical `vpn` map with each profile map, so a template default
applies when a profile omits a key. Transport egress preparation
(`ansible/playbooks/tasks/transport-egress-prepare.yml`) enables the guarded
generation for every non-subscription-only profile with Xray REALITY, XHTTP or
Hysteria, and `scripts/transport_semantics.py` refuses an explicit
`enable_transport_egress: false` for those profiles.

## Goals / Non-Goals

- Goal: remove each defect with the smallest change in the owning role.
- Goal: add a regression that fails on the current `main` for each defect.
- Non-goal: replace Xray rotation with `copytruncate`. The guarded recovery
  is the designed path; a session-preserving rotation is separate work.
- Non-goal: change the real-VPS AWG sentinel client, the AWG Go toolchain
  source, provider image allowlists, or the deploy-tooling findings
  (blue-green plan review, `BLUE_ENV`, host `env` assertion). Track those
  separately.
- Non-goal: deploy, rotate credentials or touch any host.

## Decisions

- Rotation: compute the predicate in `logrotate-xray.j2` from the same
  `vpn_subscription_only` and frontend toggles, with the same `default(true)`
  values as transport egress preparation. Rejected: `default(true)` on the
  optional toggle alone, because it still disagrees with preparation when a
  profile sets the toggle but disables every frontend.
- Resolver: remove `resolvconf` from the AmneziaWG package list and the
  Molecule debconf preseed that existed only for it. Rejected: a conditional
  install when `systemd-resolved` is absent, because no server path calls
  resolvconf.
- AWG destinations: add `firewall_awg_destination_deny_v4` and
  `firewall_awg_destination_deny_v6` to the firewall role defaults, render one
  counted drop per family per AWG instance before the established accept, and
  add a unit test that compares both lists with
  `scripts/transport_destination_policy.py`. Rejected: calling the Python
  module at render time, because the firewall template renders without
  controller-side helpers in Molecule and snapshots.
- Watchdog: add a `probe_config` helper that records the probe like
  `probe_unit` and also marks the unit in `invalid_units`. The recovery loop
  skips marked units and records `RESTART WITHHELD <unit> (config invalid)`.
  The red result, alert and non-zero exit stay unchanged. Rejected: removing
  the unit mapping from validation probes, because an inactive unit with a
  bad configuration would then still be restarted by its liveness probe.
- Hysteria: tighten the existing pre-flight assertion to the Xray regex.
  Pre-release Hysteria builds remain testable only through Molecule inputs.

## Contracts and ownership

- `ansible/roles/monitoring/templates/logrotate-xray.j2`,
  `tests/unit/test_monitoring_logrotate.py`.
- `ansible/roles/amneziawg/tasks/enable.yml`,
  `ansible/roles/amneziawg/molecule/default/prepare.yml`, a unit regression.
- `ansible/roles/firewall/defaults/main.yml`,
  `ansible/roles/firewall/templates/nftables.conf.j2`,
  `tests/unit/test_firewall_egress_policy.py` or a new focused test file.
- `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2`,
  `tests/unit/test_watchdog_state.py` or `test_watchdog_templates.py`.
- `ansible/roles/hysteria/tasks/enable.yml` and a unit regression.
- Role `CLAUDE.md` notes and `tests/snapshots/` goldens for changed templates.

## Risks / Trade-offs

- An AWG recipient that relied on a private destination loses it → this is
  the documented recipient boundary for the other transports; operators who
  need a private route use a separate reviewed forwarding contract.
- A withheld restart can leave a stopped unit down until an operator acts →
  the run stays red and alerts; a restart with an invalid configuration would
  fail in any case.
- Existing secrets with a pre-release Hysteria pin stop converging → the
  refusal happens before acquisition, so the running runtime stays in place.
- Debian 13 hosts that already lost `systemd-resolved` keep that state → the
  baseline resolver tasks run only when the service exists; recreate such a
  disposable node instead of repairing it in place.

## Migration Plan

Merge, then converge each node through the canonical dry-run and deploy path.
The dry-run shows the new logrotate policy, nftables rules and watchdog script.
Rollback is a revert commit followed by the same converge path. No secrets,
Terraform or client migration is required.
