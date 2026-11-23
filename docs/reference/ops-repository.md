# Ops repository

> **Status:** Current · **Type:** reference · **Tier:** — · **Reviewed:** 2026-11-22

The ops repository is a private GitHub repository that holds the operator inputs this public repository needs to run its Make targets: inventories, tfvars, profile overrides, SSH configuration, the SOPS recipient policy, SOPS-encrypted deployment documents, the catalog, plans and receipts. It holds no credential. CI and a Claude cloud session read it; the operator workstation keeps a clone. Which kit item goes where is defined in [the local operator kit contract](../how-to/local-operator-kit.md#mapping-to-the-ops-repository).

## Layout

```text
<ops-repo>/
  README.md                      # recovery order and break-glass pointers
  upstream.lock                  # repository URL and 40-character revision of this repository
  catalog.json                   # kit catalog; references only
  fleet.mk                       # included by the public checkout's ignored .fleet.mk
  config/
    .sops.yaml                   # recipient policy
    <scope>.secrets.sops.yaml    # deployment documents, encrypted
    inventories/<env>.ini        # canonical generated inventory
    tfvars/<provider>/<env>.tfvars
    group_vars/                  # operator profile overrides
    ssh.conf
    known_hosts
  plans/                         # operation plans as prose, never saved tfplans
  receipts/                      # grants, revocations and drills, redacted
```

Start from `templates/ops-repo/` in this repository.

## Pin

`upstream.lock` has two lines: `repository=https://github.com/po4yka/ripdpi-vpn-deploy` and `revision=<40 lowercase hex characters>`. Jobs check out exactly that revision. Change it only by pull request.

## Input wiring

The public checkout's ignored `.fleet.mk` contains one line, `include /absolute/path/to/ops/fleet.mk`. The template `fleet.mk` derives its own absolute directory and sets:

| Variable | Value | Consumers |
|---|---|---|
| `TF_BACKEND_ROOT` | `<ops>/config/backend` | Directory of reviewed `<provider>.s3.tfbackend` files for OpenTofu. Use the same directory for initialization and subsequent operations. |
| `TFVARS_ROOT` | `<ops>/config/tfvars` | `make plan` passes `<TFVARS_ROOT>/<PROVIDER>/<ENV>.tfvars` to `tofu plan`; `make inventory` reads the same files for each host pair. Empty selects `terraform/providers/<provider>/environments/<env>.tfvars`. |
| `ANSIBLE_INVENTORY` | `<ops>/config/inventories/<ENV>.ini` | `make inventory` writes it; `make dry-run` and `make deploy` pass it to the deploy controller as `DEPLOY_INVENTORY`; prechecks read it. |
| `SOPS_FILE` | `<ops>/config/<ENV>.secrets.sops.yaml` | `make decrypt`. |

`TFVARS_ROOT` must be absolute.

## Validation

Run `scripts/validate-ops-repo.py <ops checkout>` from this repository, and gitleaks, on every pull request and push of the ops repository. The validator refuses:

- a missing or loose pin (branch, tag, short or uppercase SHA, another repository);
- symbolic links;
- a fleet `*.s3.tfbackend` file with credentials (including the SSE-C encryption key `sse_customer_key`) or with missing or incorrect top-level settings for `use_lockfile = true`, `key = "state/<provider>/terraform.tfstate"`, or `workspace_key_prefix = "state/workspaces"`;
- private key material (`AGE-SECRET-KEY-`, PEM, OpenSSH or PGP private keys, WireGuard `PrivateKey =` lines) anywhere;
- state, saved plans and decrypted secret files by name (`*.tfstate`, `*.tfplan`, `*.secrets.yaml`, `*.dec`, `.env`);
- a YAML or JSON file that has a top-level section of `secrets/schema.json` but no SOPS metadata;
- a `*.sops.yaml` or `*.sops.json` document without age metadata, encrypted to a recipient that `config/.sops.yaml` does not list, or with any non-empty value that is not an `ENC[...]` string;
- a `config/.sops.yaml` that is not a list of rules with age recipients (`key_groups` is not supported);
- a `catalog.json` `credentials` entry without an `authority` value.

Inside a Git checkout it scans the files Git would commit (tracked, and untracked but not ignored); elsewhere it scans every file. Findings name the path and rule and never print content.
