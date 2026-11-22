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
2. With operator authorization, create or select the intended private repository. Run a secret-free default-branch job behind an environment with a required reviewer. Verify it waits, rejection prevents execution, and approval releases a fresh run. Record the result before importing operator data, provisioning credentials or migrating state. If the repository lacks this entitlement, pause for the operator to select an eligible owner or plan.
3. Import the non-secret kit material, run the validator and gitleaks, then compare the two-checkout plan inputs, rendered inventory and dry-run selection against the kit.
4. Rollback: point `.fleet.mk` back at `secrets/local/`; the kit was not modified.

## Open verification questions

1. Can the Claude cloud environment attach two repositories in one session (ops and public) so a pin bump can be prepared with both visible? Cloud-environment docs say yes, but repository hooks then do not run; W7 checks it.
2. Does any existing script read `secrets/local/` by a hard-coded path that `.fleet.mk` does not override? The kit contract warns that direct scripts use their own defaults; the implementation must list them with `rg -n "secrets/local" scripts vpnd`.
