# terraform/policy — Conftest / OPA policies

Cross-provider policy layer above the per-provider `tofu test` suite. Every provider plan must satisfy all rules before merge.

## Policies

| File | Rule | Deny condition |
|---|---|---|
| `server_metadata.rego` | `every_server_has_metadata_enabled` | Any supported server resource has `metadata = false` in the post-apply state. |
| `server_metadata.rego` | `server_is_not_deleted_by_an_ordinary_plan` | A plan deletes or replaces a server resource. `prevent_destroy` stops Terraform from planning that; only the temporary override of `scripts/destroy.sh` lifts it, and a plan made while the override exists is refused here. |
| `server_metadata.rego` | `active_edge_firewall_stays_active` | An `upcloud_server` plan changes `firewall` from `true` to `false` in place. |
| `server_metadata.rego` | `existing_server_gets_its_edge_firewall` | A plan changes resources while an existing `upcloud_server` keeps `firewall = false`. Within this rule (`server_is_not_deleted_by_an_ordinary_plan` refuses a replacement), the plan that creates or replaces the server, a plan that still creates its `upcloud_firewall_rules` (an interrupted first apply) and a plan with no resource change are allowed. |
| `server_metadata.rego` | `every_server_has_an_edge_firewall` | An `hcloud_server` has no `firewall_ids`, a `vultr_instance` has no `firewall_group_id` or a `scaleway_instance_server` has no `security_group_id` (a reference that is not known until apply counts as attached), or a `scaleway_instance_security_group` has `inbound_default_policy = "accept"`. |
| `secondary_ip.rego` | `no_secondary_public_ip_without_opt_in` | A server plan adds a secondary public IPv4 without `var.additional_public_ip = true`; ordinary dual-stack IPv6 is permitted. |
| `admin_port.rego` | `no_admin_port_exposed_to_world` | Any firewall resource allows the effective `var.ssh_port` or TCP/3389 from `0.0.0.0/0` or `::/0`. panel_port rules removed — no admin panel is deployed. |
| `ssh_cidrs.rego` | `firewall_rules_pin_ssh_to_documented_cidrs` | An SSH allow rule on `var.ssh_port` references a source CIDR not present in `var.allowed_ssh_cidrs`. |
| `egress_address.rego` | `retained_primary_ip_is_not_auto_deleted` | An `hcloud_primary_ip` (the egress address in `terraform/ops/egress-proxy`) does not set `auto_delete = false`, so deleting its server would delete the address that provider API allowlists name. |
| `no_secrets_in_user_data.rego` | `cloud_init_user_data_contains_no_secrets` | A server resource's `user_data` contains a line-anchored plaintext assignment matching `(password\|token\|api_key\|secret)\s*[:=]\s*[^\s]{6,}`. The bare word `key` is excluded to avoid false-positives on SSH authorized_keys lines. |

Fail-on-violation only — no `--warn` flag is passed (Open Question 6 resolution).

## Running locally

```sh
# 1. Run native provider tests; they use mock_provider and do not contact provider APIs.
tofu -chdir=terraform/providers/upcloud init -backend=false
tofu -chdir=terraform/providers/upcloud test

# 2. Verify Conftest policy modules.
conftest verify --rego-version v0 -p terraform/policy/
```

Repeat the Terraform test step with `hetzner` and `vultr` as the `-chdir` target. Do not run CI policy checks against `environments/prod.tfvars.example`; provider plans require real operator credentials and the UpCloud example intentionally contains a placeholder template UUID.

## Make targets

```sh
# native mock_provider tests, all four roots
make tf-test
# plan the environment and evaluate these policies
make PROVIDER=<p> ENV=<e> tf-conftest
```

`tf-conftest` plans through `scripts/terraform-env.sh` (requires the environment tfvars and provider credentials) and runs conftest with `--all-namespaces` against the rendered plan JSON. The shared `scripts/check-tf-plan.sh <plan.json>` gate requires a nonempty evaluation of every policy family. It rejects malformed reports as well as policy violations. Management-port checks include containing port intervals and provider defaults for unrestricted source addresses.

## Validation

Rego syntax can be checked without a running plan:

```sh
# With OPA installed:
opa fmt --diff terraform/policy/*.rego

# With Conftest installed:
conftest verify --rego-version v0 -p terraform/policy/
```

When CI selects Terraform checks, the `tf-test` job runs the provider tests and `tf-policy.yml` runs the Conftest verification once.
