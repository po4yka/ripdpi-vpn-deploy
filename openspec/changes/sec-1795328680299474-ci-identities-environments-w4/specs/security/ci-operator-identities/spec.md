## Purpose

Define the CI identities that operate the fleet from the private ops repository, the GitHub environments that hold them, which operations need a required reviewer, and how each identity is revoked without affecting the operator or other identities.

## ADDED Requirements

### Requirement: REQ-CIID-SEPARATE — Every CI identity is distinct and revocable alone

CI MUST use its own age recipient, admin SSH key, Tailnet identities and provider tokens. No CI identity MUST equal an operator identity. Revoking one CI identity MUST NOT require changing the operator's identities or any other CI identity.

#### Scenario: Revoke the CI SSH key

- **WHEN** the CI public key is removed from `admin_ssh_public_keys` and `deploy` runs
- **THEN** the key is absent from every node's admin `authorized_keys` and the operator key still logs in

#### Scenario: Revoke the CI age recipient

- **WHEN** the CI recipient is removed from `.sops.yaml` and `sops updatekeys` runs
- **THEN** new ciphertext no longer decrypts with the CI identity, and the runbook requires rotation of every secret the CI identity could read, because Git history keeps old ciphertext

### Requirement: REQ-CIID-ENV-MATRIX — Environments hold only their own credential classes

Environments MUST hold only these classes: `tofu-plan` and `tofu-apply` hold the state passphrase, B2 state keys, provider tokens and the `tag:ci-tofu` Tailnet identity; `deploy-check`, `deploy` and `ops-secrets` hold the CI age identity, CI SSH key and `tag:ci-deploy` Tailnet identity; `tailnet-policy` holds only the policy-push identity. A job MUST NOT reference a secret outside its environment.

#### Scenario: Deploy job reads a provider token

- **WHEN** a workflow job in `deploy` references `secrets.VULTR_API_KEY`
- **THEN** `scripts/validate-ops-environments.py` fails and names the job and secret

### Requirement: REQ-CIID-REVIEWERS — Mutations need a required reviewer

`tofu-apply`, `deploy`, `ops-secrets` and `tailnet-policy` MUST have a required reviewer and a deployment branch policy limited to the default branch. `tofu-plan` and `deploy-check` MUST have no reviewer and the same branch policy. apply, destroy, deploy, rotate and issue MUST run only in reviewer environments; plan, dry-run and verify MAY run in no-reviewer environments.

#### Scenario: Apply in a no-reviewer environment

- **WHEN** a workflow runs `make apply` in `tofu-plan`
- **THEN** the validator fails

#### Scenario: Reviewer missing

- **WHEN** the live environment `deploy` has no required reviewer
- **THEN** the read-only environment check (reusing `scripts/check-ci-deploy-gate.py`) fails

### Requirement: REQ-CIID-UNTRUSTED-INPUT — No-reviewer jobs never run pull-request code with secrets

No-reviewer jobs triggered by a pull request MUST run the default-branch workflow code, MUST treat pull-request files as data, and MUST refuse to load secrets when the pull request changes workflows, `fleet.mk`, `ssh.conf`, `upstream.lock` or any file that contains Jinja or Make syntax in a data field. Such pull requests MUST go through a reviewer environment. `upstream.lock` MUST name a commit that is an ancestor of the public repository's `main`.

#### Scenario: Jinja in inventory

- **WHEN** a pull request adds `{{ lookup('pipe', ...) }}` to an inventory variable
- **THEN** the PR dry-run job refuses to load secrets and asks for the reviewer path

#### Scenario: Fork commit pinned

- **WHEN** `upstream.lock` names a commit reachable only from a fork
- **THEN** the validator fails before checkout

### Requirement: REQ-CIID-LEAST-PRIVILEGE — Tokens are scoped to the fleet's needs

Each provider token MUST be limited to the project, sub-account, bucket, domain or tag the fleet uses, and `tofu-plan` MUST receive a read-only token where the provider offers one. The catalog MUST record, for each token, its scope, holder environment, expiry and revoke procedure.

#### Scenario: Catalog gap

- **WHEN** an environment secret has no catalog entry with `authority: gh-environment`
- **THEN** the ops repository validator reports the gap
