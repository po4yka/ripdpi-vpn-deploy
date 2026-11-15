# SEC-1794729384681094: Gate the UpCloud edge firewall, collector ingest and CI runner lane

## Objective

A server without a provider edge firewall, an unbounded push to the collector, a second self-hosted workflow and a hook in the agent settings are each refused by a check in the tree.

## Ownership

- `terraform/policy/`, `ansible/roles/observability_control_plane/`, the shared metric allowlist read by `ansible/roles/observability_agent/`, `.github/repository-policy.json`, `scripts/configure-repository.py`, the three `publish-*.yml` workflows, `tests/unit/test_agent_instructions.py`, their tests and snapshots.

## Execution

- [x] SEC-1794729475212458 Deny a server that stays without a provider edge firewall #bug @item:SEC-1794729384681094
- [x] SEC-1794729504775329 Apply the metric allowlist and per-node limits in the collector relay #bug @item:SEC-1794729384681094
- [x] SEC-1794729526950019 Record the fork approval setting, pin the self-hosted label and publish images only from main #bug @item:SEC-1794729384681094
- [x] SEC-1794729547422604 Refuse hooks and shell allow entries in the agent settings file #bug @item:SEC-1794729384681094

## Verification

- `make tf-policy-verify`, `make tf-test`, control-plane promtool and snapshot tests, `make molecule-test ROLE=observability_control_plane`, the workflow and agent settings unit tests, one `make check`; remote CI. The collector receives the relay change through the reviewed dry-run and deploy transaction after merge.
