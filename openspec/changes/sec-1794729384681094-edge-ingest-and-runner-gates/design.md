## Context

`proposal.md` gives the motivation. `terraform/policy/server_metadata.rego` has the `active_edge_firewall_stays_active` rule, which matches only `before.firewall == true` and `after.firewall == false`. The relay relabel template rewrites `node` and nothing else, while the agent's `prometheus.yml.j2` has `keep`, `labelkeep`, `sample_limit` and `label_limit`. `real-vps-awg-nat.yml` uses `[self-hosted, linux, ripdpi-awg-vps]` and checks `GITHUB_REF` inside the job. The tracked agent settings file holds attribution and file permission rules only.

## Goals / Non-Goals

- Goal: each of the four states is refused by a check that runs without an operator decision.
- Non-goal: a stateful UpCloud firewall or a change to the promotion flow itself.
- Non-goal: registering a self-hosted runner. The lane stays dormant.
- Non-goal: authentication on the collector's loopback Prometheus. It is a separate low finding.

## Decisions

- The UpCloud rule keys on the resource change actions: `create` passes, every other action with `after.firewall == false` is denied for a VPN server. Rejected: a bootstrap-phase variable, because the action already carries that information.
- The missing-firewall rules are one deny for each provider resource type, in the existing policy namespaces, with tests beside them.
- The relay reuses the agent's allowlist through one shared variable file, so that the two lists cannot drift. Limits use the relay's own flags for series for each hour, labels for each series and label value length. Rejected: limits in Prometheus only, because the relay is the first process that sees the push.
- The drop counter is the relay counter for which `SEC-1793790940328939` owns scraping and the alert; this change adds no second alert.
- The workflow test reads the workflow files as YAML and compares `runs-on`. The fork approval value is added to the existing policy file and to the existing check in `configure-repository.py`.
- The agent settings test goes into `tests/unit/test_agent_instructions.py`, which already owns agent file layout.

## Contracts and ownership

- Terraform: `terraform/policy/server_metadata.rego`, the firewall policy files and their `_test.rego` files.
- Ansible: `ansible/roles/observability_control_plane/templates/observability-prometheus-relay-relabel.yml.j2`, the relay unit template, and a shared allowlist variable that `ansible/roles/observability_agent/` also reads.
- CI: `.github/repository-policy.json`, `scripts/configure-repository.py`, `.github/workflows/publish-molecule-debian13.yml`, `publish-molecule-ubuntu2404.yml`, `publish-observability-kuma.yml`.
- Tests: `tests/unit/test_agent_instructions.py`, a new case in the workflow policy tests.

## Risks / Trade-offs

- A legitimate new metric is dropped until the allowlist gains it → the shared list makes the agent and the relay change together, and the drop alert reports the mismatch.
- An operator with an unpromoted UpCloud node cannot plan another change first → the denial names the promotion step, which is the intended order.
- A publish from a branch was a way to test an image → `workflow_dispatch` stays available.

## Migration Plan

Merge, promote any UpCloud node that still has the provider firewall off, then deploy the collector through the ordinary dry-run and deploy transaction. Rollback is a revert and a second collector deploy. Gates: `make tf-policy-verify`, `make tf-test`, the control-plane promtool and snapshot tests, `make molecule-test ROLE=observability_control_plane`, the unit tests named above, and one `make check` before handoff.
