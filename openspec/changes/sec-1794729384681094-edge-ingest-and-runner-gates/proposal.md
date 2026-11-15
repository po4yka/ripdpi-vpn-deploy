# Change: Gate the UpCloud edge firewall, collector ingest and CI runner lane

Task ID: `SEC-1794729384681094`

## Why

The 2026-11-15 audit found four places where a safe state depends on a manual step or on the honest side of a boundary:
- An UpCloud node starts with the provider firewall off, and promotion turns it on. The plan policy refuses only the change from on to off. A node that is never promoted passes every gate, and the guest firewall is then its only filter. The policies also accept a server with no attached firewall on the other providers.
- The collector relay rewrites the `node` label and applies no metric-name allowlist and no series or label limits. Those limits exist only in the node's own sender. One compromised node can push high-cardinality series until the collector's Prometheus runs out of memory, which stops alerting for the fleet.
- One workflow targets a self-hosted runner. A pull request from a fork can add a workflow with the same label. No runner is registered today, and nothing in the tree records the settings that a registration needs or refuses a second workflow with that label. Three image publish workflows run on a push to any branch.
- The agent settings file runs with the operator's permissions. No test refuses a hook or a shell allow entry in it.

## What Changes

- The plan policy refuses a plan that changes resources while an existing UpCloud server keeps the provider firewall off, and a server on another provider with no attached firewall or a default-accept inbound policy. First creation, promotion, the completion of an interrupted first apply and a plan with no resource change stay allowed, because recovery and `make apply` use them before promotion.
- The collector relay keeps only the sender's allowed metric names and labels, limits labels for each series, and limits unique series for each hour to one budget for each enrolled node, summed for the whole relay. The relay binary has no limit for each certificate.
- The repository policy records the fork pull-request approval setting, and the configuration check verifies it. A test refuses the self-hosted label outside the one named workflow. The image publish workflows run only on `main`.
- A test refuses hooks and shell allow entries in the tracked agent settings file.

## Capabilities

### New Capabilities

- `security/edge-ingest-and-runner-gates`: the provider edge firewall, the collector ingest path, the self-hosted runner lane and the agent settings file each have a gate in the tree.

### Modified Capabilities

- None.

## Impact

- Terraform: `terraform/policy/` and its tests.
- Ansible: `ansible/roles/observability_control_plane/` relay templates, unit, defaults and the Molecule pushes that go through the relay.
- CI: `.github/repository-policy.json`, `scripts/configure-repository.py`, the three `publish-*.yml` workflows.
- Tests: `tests/unit/test_agent_instructions.py` and a workflow policy test.
- Operations: an UpCloud node that was never promoted fails its next plan that changes a resource until the operator promotes it. A node that is never planned again is not found by this policy.
