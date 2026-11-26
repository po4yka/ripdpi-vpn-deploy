# Terraform layer

Each provider lives in its own root module under `providers/<name>/`. They share `shared/cloud-init.yaml.tftpl` for the bootstrap template.

Use OpenTofu 1.13.10 from `mise.toml`. Each provider root commits its own `.terraform.lock.hcl` so CI and operator workstations resolve the same provider builds.

## Why per-provider root modules

Terraform requires every `module "x" { source = "…" }` to use a static path; you cannot pick a provider through a variable. Per-provider roots give you a clean drop-in: the operator runs `make PROVIDER=upcloud …` (or `hetzner`, `vultr`, `scaleway`), and the Makefile `cd`s into the right directory.

## Switching providers

```bash
make PROVIDER=upcloud   init plan apply
make PROVIDER=hetzner   init plan apply
make PROVIDER=vultr     init plan apply
make PROVIDER=scaleway  init plan apply
```

The Ansible layer is provider-neutral — only the inventory render script reads the common Terraform output contract. `nat_source_port_range` is empty for stateful provider firewalls and the inert exception root. Enabled UpCloud stateless filtering exports its exact admitted return range for guest NAT.

## Native tests

Each provider root has provider-mocked `tofu test` coverage under `providers/<name>/tests/`. These tests run without contacting cloud APIs and assert the shared inventory output contract plus provider-specific firewall and server-resource invariants:

```bash
make tf-test
```

## State

OpenTofu encrypts state on the client and stores it in the S3 backend selected by `TF_BACKEND_ROOT`. Set this absolute directory in the fleet Make configuration or export it for direct script calls. Each provider's backend file must set `use_lockfile = true`, `key = "state/<provider>/terraform.tfstate"` and `workspace_key_prefix = "state/workspaces"`. Replace `<provider>` with the provider directory name. `ENV=prod` selects the legacy `default` workspace. Other environments select a workspace with the same name. Initialize the workspace before its first plan.

```bash
make PROVIDER=upcloud ENV=green init
make PROVIDER=upcloud ENV=green plan apply
```

Complete or reconcile any pending promotion or rollback on its original reviewed revision before switching. A retained snapshot from the old revision does not bind its backend. After upgrading the wrapper, run `make init` once for each selected provider and environment. OpenTofu reads the existing remote state. The local initialization cache and the plan encryption scope now depend on the exact backend file and workspace. After any backend file edit, initialize again and generate a new plan. Regenerate plans saved with an earlier release before applying them. The state encryption key is unchanged.

`make plan` uses the read-only state identity without taking the writer lock. It saves an encrypted plan and checks its policy. Use the writer identity for `make apply`. OpenTofu takes the backend lock and checks the saved plan against the current state before it writes.

Operator scripts and `vpnd` use `scripts/terraform-env.sh`; do not invoke raw `tofu output`, `plan`, or `apply`, because it can select the wrong workspace. Back up state out-of-band; without it Terraform cannot follow blue-green or rotate the floating IP. See `docs/how-to/incident.md` § "State loss".

## Public listener contract

`public_listeners` in each environment tfvars is the typed provider-edge allowlist. `render-inventory.sh` exports its resolved value to Ansible; `site.yml` fails before mutation unless it exactly matches the enabled runtime listener manifest. The firewall role and `security-verify.yml` consume the same contract. Update it whenever enabling an optional listener, multi-cohort port, or port-hopping range; do not add static provider firewall rules by hand. An environment that leaves `public_listeners` empty fails the plan unless it explicitly sets `use_legacy_public_listeners = true` to inherit the historical default set.

Each provider/environment contract is tied to the Ansible cohort deployed for that environment. If `COHORTS` selects a different profile, change and validate `public_listeners` in the matching tfvars before `make plan apply`; the fail-closed pre-task intentionally rejects a mismatched profile.

## Plan policy enforcement

The Rego rules under `terraform/policy/` gate plans through conftest in two places. PR CI (`tf-policy.yml`) runs their unit tests once and, for the roots whose SDK tolerates credential-shaped dummies at configure time (`hetzner`, `vultr`), renders an offline plan and evaluates the full rule set against it. `make plan` evaluates its saved plan for every provider. `make apply` checks the same plan again before applying it. `make tf-conftest` can check a separate preview with the same input file.

For production migration acceptance, select one reviewed Git revision and record its full SHA. Initialize each authorized provider and environment. With the read-only identity, run the following command separately for each workspace:

```bash
TF_CLI_ARGS_plan=-detailed-exitcode make PROVIDER="$provider" ENV="$environment" plan
```

A change or planning error stops Make before policy evaluation. A successful command proves that the saved plan has no changes and passes policy. Record the revision, tool version, workspace and result in the private receipt. Keep the encrypted plan private.

## Providers

| Provider | Lock version | Notes |
|---|---|---|
| `upcloud` | 5.43.0 | Uses `UpCloudLtd/upcloud`. |
| `hetzner` | 1.68.0 | Uses `hetznercloud/hcloud`. Export `HCLOUD_TOKEN` before planning. |
| `vultr` | 2.32.0 | Uses `vultr/vultr`. Export `VULTR_API_KEY` before planning. |
| `scaleway` | 2.78.0 | Uses `scaleway/scaleway`. Export `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, and `SCW_DEFAULT_PROJECT_ID` before planning. |

The committed `.terraform.lock.hcl` files are authoritative; this summary is updated when those locks change.
