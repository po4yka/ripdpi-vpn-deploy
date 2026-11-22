## Context

The kit layout and catalog fields are defined in `docs/how-to/local-operator-kit.md`. The current plan recipe selects a provider-relative tfvars file. The deploy controller opens `ansible/inventory/generated.ini` in the public checkout. W1 must change both consumers.

## Goals / Non-Goals

- Goal: one private repository that CI and the Claude cloud session can read, holding everything needed to run the public Make targets except credentials.
- Goal: each kit item has exactly one authority.
- Non-goal: storing any decryptable-by-CI operator credential, or any break-glass identity, in Git.
- Non-goal: workflows (W7) and environments (W4).

## Decisions

- Ops repository layout:

```text
<ops-repo>/
  README.md                    # recovery order and break-glass pointers
  upstream.lock                # repo URL + 40-hex SHA of po4yka/ripdpi-vpn-deploy
  catalog.json                 # kit catalog; references only, adds "authority"
  fleet.mk                     # included by the public checkout's .fleet.mk
  config/
    .sops.yaml                 # recipient policy: operator break-glass + CI (W4)
    <scope>.secrets.sops.yaml  # existing deployment schema per scope, encrypted
    inventories/<env>.ini       # canonical generated INI format consumed by deploy
    tfvars/<root>/<env>.tfvars
    backend/<root>.s3.tfbackend   # W3, no credentials
    group_vars/                # operator profile overrides
    ssh.conf
    known_hosts
  plans/                       # operation plans (prose), not saved tfplans
  receipts/                    # grants, revocations, drills; redacted
  requests/                    # W7 operation requests
  .github/workflows/           # W7
```

- Kit mapping (`REQ-OPSREPO-KIT-MAP`):

| Kit path | Authority after migration | Notes |
|---|---|---|
| `README.md` | ops repo `README.md` | Recovery order rewritten for remote state. |
| `catalog.json` | ops repo `catalog.json` | Adds `authority` field: `ops-repo`, `b2-recovery`, `gh-environment`, `password-manager`, `temporary`. |
| `config/age.key` | password manager (break-glass) | Operator key leaves daily use; CI uses its own recipient (W4). |
| `config/.sops.yaml` | ops repo | Public recipients only. |
| `config/<scope>.secrets.sops.yaml` | ops repo | Re-encrypted to operator + CI recipients in W4. |
| `config/operator-access.sops.yaml` | B2 recovery prefix | Encrypted to the operator recipient only; Git history would keep every old ciphertext forever. |
| `config/fleet.mk`, `ssh.conf`, `known_hosts` | ops repo | Reviewed as executable configuration. |
| `keys/` | password manager or hardware token | CI SSH key is a separate identity in a GitHub environment (W4). |
| `plans/` | ops repo `plans/` | Saved `.tfplan` files stay temporary and encrypted (W3). |
| `clients/<device-id>/` | temporary | Delivered encrypted to the recipient age key (W7). |
| `state-backups/` | B2 recovery prefix | Replaced by versioned, object-locked remote state (W3). |
| `receipts/` | ops repo `receipts/` | No token-bearing URLs. |
| `recovery/` | B2 recovery prefix | Sealed archive; unlock factor in the password manager. |
| `runtime/` | temporary | Runner temp directory only. |

- Implemented wiring: `TFVARS_ROOT` (absolute, empty by default) selects `<root>/<provider>/<env>.tfvars` for `make plan` and for every host pair in `render-inventory.sh`; `make inventory` writes `ANSIBLE_INVENTORY` through `INVENTORY_OUTPUT`; `make dry-run`/`make deploy` capture `ANSIBLE_INVENTORY` literally like the other caller inputs and export it as `DEPLOY_INVENTORY`, which the controller reads instead of `ansible/inventory/generated.ini`. The template `fleet.mk` sets all three from its own absolute directory.
- W1 owns the external paths end to end. The reviewed `fleet.mk` supplies absolute paths to the selected tfvars and canonical INI inventory. `make plan` validates and passes the same tfvars path to the CLI. `make inventory` writes the selected inventory, and `make dry-run` and `make deploy` pass that path to the controller's existing snapshot and validation code. Preserve local defaults and keep operator files in the ops checkout. Test separate checkouts with conflicting local defaults so a fallback cannot pass by accident.
- Validator: `scripts/validate-ops-repo.py` in the public repository (stdlib only) checks the pin format, rejects private-key and age-identity markers, plaintext secret files, `*.tfstate`, `*.tfplan`, SOPS files without metadata or with recipients outside `.sops.yaml`, and catalog entries without an allowed `authority`. Gitleaks runs beside it. Rejected: a new dependency for YAML parsing; SOPS metadata detection needs only a key check and PyYAML is already in `requirements.txt`.
- Pin updates: a cloud session or Dependabot-like workflow opens a PR that changes `upstream.lock`; W7 runs plan and dry-run on the PR.

## Contracts and ownership

- Owned paths: `docs/how-to/local-operator-kit.md`, `docs/reference/ops-repository.md`, `templates/ops-repo/**`, `scripts/validate-ops-repo.py`, `tests/unit/test_validate_ops_repo.py`, `docs/README.md` index entry. Include `Makefile`, `scripts/render-inventory.sh`, `scripts/deploy-controller.py` and their matching tests.
- The deployment secrets schema (`secrets/schema.json`) is unchanged.

## Risks / Trade-offs

- A private repository is readable by every collaborator and by the Claude cloud session → it holds no credential; node addresses are the accepted exposure.
- Git history is permanent → encrypted documents that CI can decrypt are rotated by re-issuing secrets, not by rewriting history; operator-only material stays out of Git.
- Two copies during migration → `REQ-OPSREPO-ROLLBACK` keeps the kit authoritative until equality is shown.

## Migration Plan

1. Land template, validator and docs (local, reversible).
2. With operator authorization, create the intended private repository (forking disabled). Environment required reviewers are not available for private repositories on the operator's GitHub Pro plan (GitHub documentation, checked 2026-11-22), so the operator chose the merge as the approval. Add a default-branch ruleset that blocks direct pushes, force pushes and deletion and lets only repository administrators bypass it, by pull request. Prove it before importing operator data: read the effective rules of the default branch, show that a direct push by the operator is refused, and merge a pull request as the operator. Record the result. Private-repository Actions are unavailable until the account billing is fixed (2026-11-22), so the secret-free job that shows the workflow `GITHUB_TOKEN` refused runs with W4's first Actions use; its probe workflow stays in the repository until then.
3. Import the non-secret kit material, run the validator and gitleaks, then compare the two-checkout plan inputs, rendered inventory and dry-run selection against the kit.
4. Rollback: point `.fleet.mk` back at `secrets/local/`; the kit was not modified.

## Open verification questions

1. Can the Claude cloud environment attach two repositories in one session (ops and public) so a pin bump can be prepared with both visible? Cloud-environment docs say yes, but repository hooks then do not run; W7 checks it.
2. Does any existing script read `secrets/local/` by a hard-coded path that `.fleet.mk` does not override? The kit contract warns that direct scripts use their own defaults; the implementation must list them with `rg -n "secrets/local" scripts vpnd`. Answered during implementation: only `scripts/check-vpnd-package.py` (refuses kit paths in the package) and `scripts/private_client_artifact.py` (allows private artifacts outside the repository or under the kit) name it, and both accept an ops checkout outside the repository. Operator scripts that derive the provider-root tfvars path themselves (`destroy.sh`, `blue-green.sh`, `drift-since-tag.sh`, `vpnd`) still read it; they are outside the W1 consumers (plan, inventory, deploy controller) and W7 must route them or keep them on the kit.
