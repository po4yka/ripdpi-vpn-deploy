## Context

`proposal.md` gives the motivation. `terraform/policy/server_metadata.rego` has the `active_edge_firewall_stays_active` rule, which matches only `before.firewall == true` and `after.firewall == false`. The relay relabel template rewrites `node` and nothing else, while the agent's `prometheus.yml.j2` has `keep`, `labelkeep`, `sample_limit` and `label_limit`. `real-vps-awg-nat.yml` uses `[self-hosted, linux, ripdpi-awg-vps]` and checks `GITHUB_REF` inside the job. The tracked agent settings file holds attribution and file permission rules only.

## Goals / Non-Goals

- Goal: each of the four states is refused by a check that runs without an operator decision.
- Non-goal: a stateful UpCloud firewall or a change to the promotion flow itself.
- Non-goal: registering a self-hosted runner. The lane stays dormant.
- Non-goal: authentication on the collector's loopback Prometheus. It is a separate low finding.

## Decisions

- The UpCloud rule keys on the resource change actions: a server action that contains `create` passes, and every other action with `after.firewall == false` is denied when the plan changes a resource. Two more plans pass, because existing flows need them before promotion: a plan that still creates `upcloud_firewall_rules` (`make apply` or recovery finishes an interrupted first apply), and a plan with no resource change (`scripts/recovery.py` admits an empty plan through the same policy to prove convergence). The rule covers every `upcloud_server`, not only `node_purpose = "vpn"`: observer and split-hop nodes use the same flag. The disposable CI lane plans one creation and one destruction, so it is not affected. Rejected: a bootstrap-phase variable, because the action already carries that information. Rejected: denial of every plan that is not a creation, because it stops recovery and the completion of a first apply.
- The missing-firewall rules are one deny for each provider resource type, in the existing policy namespaces, with tests beside them.
- The relay repeats the agent's allowlist as literals, and a unit test renders both templates and fails when they differ. Rejected: one shared variable. `test_scrapes_have_explicit_sample_and_label_bounds` requires the lists to be literals in the sender template and refuses allowlist variable names, so that private variables cannot widen the metric contract. The relay also admits `up` with the `instance` label, which the sender creates for each scrape target. Limits use the flags of the pinned vmagent 1.155.0: `-maxLabelsPerTimeseries`, `-maxLabelNameLen`, `-maxLabelValueLen` and `-remoteWrite.maxHourlySeries`. The hourly limit is one value for the whole relay; it is `relay_series_per_node` (2200, the tested capacity for each node) times the number of enrolled identities. vmagent has no limit for each ingress identity, so one node can use the budget of the others for new series until the hour ends. Rejected: limits in Prometheus only, because the relay is the first process that sees the push.
- The enabled Molecule scenario pushes fixture series through the real relay. Those pushes now use allowlisted names and labels, and the fixture raises `relay_series_per_node` for its one identity. No Molecule case for a push over the limit is added in this change.
- The relay counts rejected series in `vmagent_hourly_series_limit_rows_dropped_total` and `vm_rows_ignored_total` on its own metrics endpoint. `SEC-1793790940328939` owns scraping and the alert; this change adds neither.
- The workflow test reads the workflow files as YAML and compares `runs-on`. The test also refuses matrix runner values and runner groups outside the hosted set. The fork approval value is added to the existing policy file and to the existing plan in `configure-repository.py`, which lists a change when the live value differs, fails the apply readback while it differs, and refuses a weaker recorded value.
- The agent settings test goes into `tests/unit/test_agent_instructions.py`, which already owns agent file layout.

## Contracts and ownership

- Terraform: `terraform/policy/server_metadata.rego`, the firewall policy files and their `_test.rego` files.
- Ansible: `ansible/roles/observability_control_plane/templates/observability-prometheus-relay-relabel.yml.j2`, the relay unit template, the `relay_series_per_node` default and its assertion, and the enabled Molecule fixture. `ansible/roles/observability_agent/` templates do not change.
- CI: `.github/repository-policy.json`, `scripts/configure-repository.py`, `.github/workflows/publish-molecule-debian13.yml`, `publish-molecule-ubuntu2404.yml`, `publish-observability-kuma.yml`.
- Tests: `tests/unit/test_agent_instructions.py`, a new case in the workflow policy tests.

## Risks / Trade-offs

- A legitimate new metric is dropped until the allowlist gains it → the unit test makes the agent and the relay change together.
- One node can use the whole hourly series budget → the collector stays inside its memory limit, and series that other nodes already send continue; only new series wait for the next hour.
- An operator with an unpromoted UpCloud node cannot apply another change first → the denial names the promotion step, which is the intended order.
- A node that is never planned again is not found → the policy reads plans only; a live check belongs to deployment acceptance.
- A publish from a branch was a way to test an image → `workflow_dispatch` stays available.

## Migration Plan

Merge, promote any UpCloud node that still has the provider firewall off, then deploy the collector through the ordinary dry-run and deploy transaction. Rollback is a revert and a second collector deploy. Gates: `make tf-policy-verify`, `make tf-test`, the control-plane promtool and snapshot tests, `make molecule-test ROLE=observability_control_plane`, the unit tests named above, and one `make check` before handoff.
