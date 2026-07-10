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
`hetzner`, `vultr`), and the Makefile `cd`s into the right directory.

## Switching providers

```bash
make PROVIDER=upcloud   init plan apply
make PROVIDER=hetzner   init plan apply
make PROVIDER=vultr     init plan apply
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
```

## State

State is local by default and isolated by provider plus `ENV`. The legacy `ENV=prod` deployment remains in Terraform's `default` workspace so existing state keeps working; every other environment uses a workspace with the same name, stored under `terraform.tfstate.d/<ENV>/`. Before using a new environment, run its initialization explicitly:

```bash
make PROVIDER=upcloud ENV=green init
make PROVIDER=upcloud ENV=green plan apply
```

Operator scripts and `vpnd` use `scripts/terraform-env.sh`; do not invoke raw `terraform output`, `plan`, or `apply`, because it can select the wrong workspace. Back up state out-of-band; without it Terraform cannot follow blue-green or rotate the floating IP. See `docs/RUNBOOK-incident.md` § "State loss".

## Providers

| Provider | Status | Notes |
|---|---|---|
| `upcloud` | primary (v1) | Uses `UpCloudLtd/upcloud`. Region `fi-hel1` recommended for EU baseline. |
| `hetzner` | implemented (v1.1) | Uses `hetznercloud/hcloud`. Export `HCLOUD_TOKEN` before planning. |
| `vultr`   | implemented (v1.1) | Uses `vultr/vultr`. Export `TF_VAR_vultr_api_key` before planning. |
