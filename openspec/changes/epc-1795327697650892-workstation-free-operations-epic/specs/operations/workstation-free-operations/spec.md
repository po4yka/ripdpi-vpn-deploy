## Purpose

Define the ordering, secret-placement and acceptance rules that let a Claude cloud session, repository CI and one egress VPS operate the whole VPN service while the operator workstation is off.

## ADDED Requirements

### Requirement: REQ-WFO-ORDER — Child changes respect dependencies

The program MUST keep these `blocked_by` edges: W2 none; W1 none; W3 on W1 and W2; W4 on W1; W5 on W2, W3 and W4; W6 on W2, W3 and W5; W7 on W1, W3, W4, W5 and W6.

#### Scenario: Dependent starts early

- **WHEN** an operator starts W3 while W2 is not done
- **THEN** `./taskctl ready` does not list W3 and `./taskctl validate` records the open blocker

### Requirement: REQ-WFO-NO-CLOUD-SECRETS — The cloud session holds no credential

No child change MUST place a provider token, age identity, SSH private key, Tailnet credential, decrypted SOPS value or OpenTofu state passphrase in the Claude cloud environment, its setup script, its repository checkout or its transcript. The cloud session MUST act only through Git pushes, pull requests and the workflow triggers that W7 defines.

#### Scenario: Cloud environment review

- **WHEN** W7 configures the Claude cloud environment
- **THEN** its environment variable list is empty of credentials and the setup script installs only pinned public toolchains

### Requirement: REQ-WFO-PUBLIC-HYGIENE — The public repository shows no operational data

No child change MUST cause a node IP address, inventory, tfvars value, deploy log, plan output or receipt to appear in a workflow run, artifact, cache or log of the public `po4yka/ripdpi-vpn-deploy` repository. Credentialed and operator-data jobs MUST run only in the private ops repository.

#### Scenario: Public workflow audit

- **WHEN** a child change adds or edits a workflow
- **THEN** the workflow lives in the ops repository, or it is a public workflow that reads no operator data and no credential

### Requirement: REQ-WFO-BREAK-GLASS — The workstation remains a working fallback

After the program closes, the operator MUST still be able to plan, apply, deploy and recover from the MacBook with the break-glass operator age key and operator tokens, against the same remote state and ops repository, without a second state copy.

#### Scenario: GitHub is unavailable

- **WHEN** GitHub Actions is down and a node must be recreated
- **THEN** the operator runs the documented break-glass procedure from the MacBook against the B2 state and succeeds

### Requirement: REQ-WFO-ACCEPT — The program is proven with the workstation off

The program MUST NOT close until one recorded drill, with the MacBook powered off, shows a Claude cloud session change a non-secret setting through a pull request, and CI plan, apply, dry-run, deploy, verify and issue one device without operator workstation involvement other than merges from a phone.

#### Scenario: Workstation-off drill

- **WHEN** the operator runs the W7 acceptance drill with the MacBook off
- **THEN** the drill receipt in the ops repository links each workflow run and records a passed verify
