## Purpose

Define the private ops repository that holds sensitive, non-secret operator configuration, pins the public deployment repository by commit SHA, and replaces the workstation-only operator kit as the shared source for CI and cloud sessions.

## ADDED Requirements

### Requirement: REQ-OPSREPO-PIN — The public repository is pinned by full SHA

The ops repository MUST record the public repository URL and a 40-character commit SHA in `upstream.lock`. Workflows MUST check out exactly that SHA. A branch name, tag or short SHA MUST fail validation.

#### Scenario: Pin is a branch name

- **WHEN** `upstream.lock` contains `main` instead of a SHA
- **THEN** `scripts/validate-ops-repo.py` exits non-zero and names the field

#### Scenario: Pin bump

- **WHEN** a pull request changes the SHA in `upstream.lock`
- **THEN** W7 runs no credentialed preview of the new pin before the operator merges it

### Requirement: REQ-OPSREPO-NO-PLAINTEXT — No plaintext secret enters the ops repository

The ops repository MUST NOT contain an age identity, SSH private key, provider token, decrypted SOPS document, OpenTofu state or saved plan. Every `*.sops.yaml` file MUST carry SOPS metadata with only the recipients in the committed recipient policy. The validator and gitleaks MUST run on every pull request and push.

#### Scenario: Decrypted file committed

- **WHEN** a commit adds a YAML file with deployment secret keys and no `sops` metadata
- **THEN** the validator fails and the pull request cannot merge

#### Scenario: Private key committed

- **WHEN** a file contains `AGE-SECRET-KEY-` or an OpenSSH private key header
- **THEN** the validator fails and prints the path, never the content

### Requirement: REQ-OPSREPO-KIT-MAP — Every kit item has one destination

Each item class of the operator kit layout MUST map to exactly one authority: the ops repository, the B2 recovery prefix, a GitHub environment secret, the operator password manager, or temporary storage only. The catalog MUST record the destination of each entry. Operator break-glass identities MUST NOT be stored in the ops repository or in GitHub.

#### Scenario: Catalog entry without destination

- **WHEN** a catalog entry has no `authority` value from the allowed set
- **THEN** the validator fails

### Requirement: REQ-OPSREPO-PUBLIC-HYGIENE — Operator data stays out of the public repository

Node addresses, inventories, tfvars values, receipts and deploy output MUST appear only in the private ops repository and its workflow logs. The public repository template and docs MUST use placeholders only.

#### Scenario: Template review

- **WHEN** `templates/ops-repo/` is rendered for documentation
- **THEN** it contains no address, account ID or hostname other than documentation placeholders

### Requirement: REQ-OPSREPO-ROLLBACK — The MacBook kit stays usable until cut-over is verified

The migration MUST keep the existing `secrets/local/` kit unchanged until the ops repository clone, used through `.fleet.mk`, produces the same rendered inventory and the same `make dry-run` input set as the kit. Plan, inventory generation and the deploy controller MUST honor the selected external input paths through the normal Make targets.

#### Scenario: Import mismatch

- **WHEN** the rendered inventory from the ops repository differs from the kit's
- **THEN** cut-over stops and the kit remains the authority

#### Scenario: Separate checkouts

- **WHEN** both checkouts contain different fixture inputs and the ops paths are selected
- **THEN** the CLI receives the ops tfvars, inventory generation writes the selected INI file and the deploy controller validates and selects its hosts

### Requirement: REQ-OPSREPO-MERGE-GATE — Only the operator can land changes

Before operator inputs are imported, the effective rules of the default branch MUST block deletion, force pushes and direct updates and require a pull request, a direct push by the operator MUST be refused, and the operator MUST be able to merge a pull request. The workflow-token refusal is proven under `REQ-CIID-MERGE-GATE` once Actions run.

#### Scenario: Private repository cannot enforce the merge gate

- **WHEN** the effective rules allow a direct update of the default branch, or the operator cannot merge
- **THEN** W1 stops before cut-over, credential provisioning or state migration
