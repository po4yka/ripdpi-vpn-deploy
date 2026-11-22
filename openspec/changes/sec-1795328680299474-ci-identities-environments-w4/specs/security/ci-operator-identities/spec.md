## Purpose

Define the CI identities that operate the fleet from the private ops repository, the GitHub environments that hold them, which operations need a required reviewer, and how each identity is revoked without affecting the operator or other identities.

## ADDED Requirements

### Requirement: REQ-CIID-SEPARATE — Every CI identity is distinct and revocable alone

CI MUST use its own age recipient, admin SSH key, Tailnet identities and provider tokens. No CI identity MUST equal an operator identity. Revoking one CI identity MUST NOT require changing the operator's identities or any other CI identity.

#### Scenario: Revoke the CI SSH key

- **WHEN** the CI public key is removed from `admin_ssh_public_keys` and `deploy` runs
- **THEN** the key is absent from every node's admin `authorized_keys` and the operator key still logs in

#### Scenario: Revoke the CI age recipient

- **WHEN** the operator removes the CI recipient, updates recipients, rotates each affected document's SOPS data key and then replaces exposed credentials
- **THEN** neither the removed identity nor a data key recovered from a historical fixture can decrypt the replacement values, and the operator can decrypt them

### Requirement: REQ-CIID-ENV-MATRIX — Environments hold only their own credential classes

Environments MUST hold only these classes: `tofu-plan` and `tofu-apply` hold the state passphrase, the scoped state bucket identities, provider tokens and the `tag:ci-tofu` Tailnet identity; `deploy-check` and `deploy` hold the CI age identity, CI SSH key and `tag:ci-deploy` Tailnet identity; `ops-secrets` holds only the CI age identity for offline preparation; `tailnet-policy` holds only the policy-push identity. A job MUST NOT reference a secret outside its environment.

#### Scenario: Deploy job reads a provider token

- **WHEN** a workflow job in `deploy` references `secrets.VULTR_API_KEY`
- **THEN** `scripts/validate-ops-environments.py` fails and names the job and secret

### Requirement: REQ-CIID-MERGE-GATE — Mutations run only after the operator merges

A ruleset on the ops repository's default branch MUST forbid direct pushes, force pushes and deletion and MUST let only repository administrators, which means the operator, merge into it. GitHub App and workflow identities, including the Claude GitHub App and `GITHUB_TOKEN`, MUST NOT be able to update the default branch. The operator's merge is the approval.

#### Scenario: Non-owner merge

- **WHEN** the Claude GitHub App or a workflow `GITHUB_TOKEN` tries to merge a pull request into, or push to, the default branch
- **THEN** the ruleset rejects the update

### Requirement: REQ-CIID-MUTATION-TRIGGER — Mutations run from the default branch only

Every environment MUST have a deployment branch policy limited to the default branch. apply, destroy, deploy, rotate, issue and Tailnet policy pushes MUST run only from workflows triggered by a push to the default branch, in `tofu-apply`, `deploy`, `ops-secrets` or `tailnet-policy`. Plan, dry-run and verify MAY run in `tofu-plan` and `deploy-check` from pull-request previews or schedules.

#### Scenario: Apply in a preview environment

- **WHEN** a workflow runs `make apply` in `tofu-plan`
- **THEN** the validator fails

#### Scenario: Mutation on a pull-request event

- **WHEN** a job in `deploy` is triggered by `pull_request_target`
- **THEN** the validator fails, and the environment branch policy refuses the job

### Requirement: REQ-CIID-UNTRUSTED-INPUT — Pull-request jobs never run pull-request code with secrets

Automatic credentialed previews MUST use trusted default-branch code and trust settings. They MAY overlay only explicitly allowed typed fields on existing targets. Other changes MUST NOT receive credentials before the operator merges them. These include changes to target addresses, SSH settings and host pins, backend endpoints, recipient policy, workflows, Make inputs and `upstream.lock`. The pin MUST be an ancestor of public `main`.

#### Scenario: Jinja in inventory

- **WHEN** a pull request adds `{{ lookup('pipe', ...) }}` to an inventory variable
- **THEN** the PR dry-run job refuses to load secrets and defers the preview until after merge

#### Scenario: Target and host pin change together

- **WHEN** a PR replaces an inventory address and its `known_hosts` entry using plain values
- **THEN** the automatic preview obtains no credential and opens no connection

#### Scenario: Fork commit pinned

- **WHEN** `upstream.lock` names a commit reachable only from a fork
- **THEN** the validator fails before checkout

### Requirement: REQ-CIID-LEAST-PRIVILEGE — Tokens are scoped to the fleet's needs

Each provider token MUST be limited to the project, sub-account, bucket, domain or tag the fleet uses, and `tofu-plan` MUST receive a read-only token where the provider offers one. The catalog MUST record, for each token, its scope, holder environment, expiry and revoke procedure.

#### Scenario: Catalog gap

- **WHEN** an environment secret has no catalog entry with `authority: gh-environment`
- **THEN** the ops repository validator reports the gap
