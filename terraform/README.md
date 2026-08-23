# Terraform layer

Each provider lives in its own root module under `providers/<name>/`. They
share `shared/cloud-init.yaml.tftpl` for the bootstrap template.

Use Terraform >= 1.15. Each provider root commits its own
`.terraform.lock.hcl` so CI and operator workstations resolve the same provider
builds.

## Why per-provider root modules

Terraform requires every `module "x" { source = "…" }` to use a static
path; you cannot pick a provider through a variable. Per-provider roots
give you a clean drop-in: the operator runs `make PROVIDER=upcloud …` (or
`hetzner`, `vultr`, `scaleway`), and the Makefile `cd`s into the right directory.

## Switching providers

```bash
make PROVIDER=upcloud   init plan apply
make PROVIDER=hetzner   init plan apply
make PROVIDER=vultr     init plan apply
make PROVIDER=scaleway  init plan apply
```

The Ansible layer is provider-neutral — only the inventory render script
reads provider-specific Terraform outputs.

## Native tests

Each provider root has provider-mocked `terraform test` coverage under
`providers/<name>/tests/`. These tests run without contacting cloud APIs
and assert the shared inventory output contract plus provider-specific
firewall and server-resource invariants:

```bash
terraform -chdir=terraform/providers/upcloud init -backend=false
terraform -chdir=terraform/providers/upcloud test

terraform -chdir=terraform/providers/hetzner init -backend=false
terraform -chdir=terraform/providers/hetzner test

terraform -chdir=terraform/providers/vultr init -backend=false
terraform -chdir=terraform/providers/vultr test

terraform -chdir=terraform/providers/scaleway init -backend=false
terraform -chdir=terraform/providers/scaleway test
```

## State

State is local by default and isolated by provider plus `ENV`. The legacy `ENV=prod` deployment remains in Terraform's `default` workspace so existing state keeps working; every other environment uses a workspace with the same name, stored under `terraform.tfstate.d/<ENV>/`. Before using a new environment, run its initialization explicitly:

```bash
make PROVIDER=upcloud ENV=green init
make PROVIDER=upcloud ENV=green plan apply
```

Operator scripts and `vpnd` use `scripts/terraform-env.sh`; do not invoke raw `terraform output`, `plan`, or `apply`, because it can select the wrong workspace. Back up state out-of-band; without it Terraform cannot follow blue-green or rotate the floating IP. See `docs/RUNBOOK-incident.md` § "State loss".

## Public listener contract

`public_listeners` in each environment tfvars is the typed provider-edge allowlist. `render-inventory.sh` exports its resolved value to Ansible; `site.yml` fails before mutation unless it exactly matches the enabled runtime listener manifest. The firewall role and `security-verify.yml` consume the same contract. Update it whenever enabling an optional listener, multi-cohort port, or port-hopping range; do not add static provider firewall rules by hand. An environment that leaves `public_listeners` empty fails the plan unless it explicitly sets `use_legacy_public_listeners = true` to inherit the historical default set.

Each provider/environment contract is tied to the Ansible cohort deployed for that environment. If `COHORTS` selects a different profile, change and validate `public_listeners` in the matching tfvars before `make plan apply`; the fail-closed pre-task intentionally rejects a mismatched profile.

## Plan policy enforcement

The Rego rules under `terraform/policy/` gate plans through conftest in two places. PR CI (`tf-policy.yml`) runs their unit tests for every provider and, for the roots whose SDK tolerates credential-shaped dummies at configure time (`hetzner`, `vultr`), renders an offline plan and evaluates the full rule set against it. Operator environments must run `make PROVIDER=<p> ENV=<e> tf-conftest` before every apply; this is the only enforcement point for `upcloud` and `scaleway`, whose providers cannot render a credential-free plan.

## Providers

| Provider | Lock version | Notes |
|---|---|---|
| `upcloud` | 5.43.0 | Uses `UpCloudLtd/upcloud`. |
| `hetzner` | 1.68.0 | Uses `hetznercloud/hcloud`. Export `HCLOUD_TOKEN` before planning. |
| `vultr` | 2.32.0 | Uses `vultr/vultr`. Export `VULTR_API_KEY` before planning. |
| `scaleway` | 2.78.0 | Uses `scaleway/scaleway`. Export `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, and `SCW_DEFAULT_PROJECT_ID` before planning. |

The committed `.terraform.lock.hcl` files are authoritative; this summary is
updated when those locks change.
