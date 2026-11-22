## Purpose

Define the private ops repository workflows that run every infrastructure, deployment, verification, rotation, issuance and DNS operation from reviewed request files, so a secretless Claude cloud session can operate the service through pull requests while CI holds and uses all credentials.

## ADDED Requirements

### Requirement: REQ-OPSWF-REQUEST — Operations are explicit, validated request files

Every operation MUST come from a file `requests/<request-id>.yaml` that names one operation from the fixed set in `design.md`, its targets and its parameters. `scripts/validate-ops-request.py` MUST reject unknown operations or targets, secret-looking values and Jinja or shell syntax. A pull request that changes configuration MUST include a request, `none` included.

#### Scenario: Unknown operation

- **WHEN** a request names `operation: shell`
- **THEN** validation fails before any secret is loaded

#### Scenario: Config change without request

- **WHEN** a pull request edits an inventory and adds no request file
- **THEN** the PR check fails and asks for a request

### Requirement: REQ-OPSWF-PREVIEW — Pull requests get plan and dry-run without approval

For a pull request from a same-repository branch, CI MUST run, with default-branch workflow code and no reviewer, `tofu plan` for every affected root and environment and `make dry-run` for every affected host, and MUST post a redacted summary to the pull request. When the pull request changes executable configuration (`REQ-CIID-UNTRUSTED-INPUT`), the preview MUST run only after reviewer approval.

#### Scenario: Toggle change

- **WHEN** a cloud session opens a pull request that changes a protocol toggle for one node
- **THEN** the PR shows a dry-run summary for that node within the same run and no secret appears in the log

### Requirement: REQ-OPSWF-EXECUTE-ONCE — Merged requests run once behind a reviewer

On merge, each new request MUST run exactly once in the environment its operation maps to, after required-reviewer approval. Deploy MUST follow the canonical dry-run then deploy sequence. Apply and destroy MUST apply the encrypted saved plan whose hash the reviewer approved. A request whose receipt already exists MUST NOT run again.

#### Scenario: Re-run of a merged workflow

- **WHEN** an operator re-runs the merge workflow for a request that already has a success receipt
- **THEN** the job exits without acting and records the skip

#### Scenario: Plan changed after approval

- **WHEN** the saved plan hash differs from the approved one at apply time
- **THEN** apply stops and asks for a new plan

### Requirement: REQ-OPSWF-SECRETS-IN-CI — Secrets are created and rotated only inside CI

Rotation and issuance MUST generate secret material inside an `ops-secrets` job, write it only to SOPS-encrypted documents, and open a pull request with the encrypted change and a follow-up deploy request. No workflow MUST print, upload or commit plaintext secret material.

#### Scenario: Rotation

- **WHEN** a merged `rotate-credentials` request runs
- **THEN** a new pull request contains only changed `*.sops.yaml` files and a deploy request, and the job log contains no secret value

### Requirement: REQ-OPSWF-CLIENT-ENCRYPTION — Client configurations leave CI encrypted

An `issue-device` request MUST carry the recipient's age public key. Every client configuration, URL or QR code MUST be encrypted to that key before upload as an artifact with short retention. An upload step MUST refuse a file that is not an age ciphertext.

#### Scenario: Missing recipient key

- **WHEN** an `issue-device` request has no recipient key
- **THEN** validation fails and nothing is issued

#### Scenario: Plaintext artifact

- **WHEN** a step tries to upload a plaintext client configuration
- **THEN** `scripts/encrypt-client-artifact.sh --check` fails the job

### Requirement: REQ-OPSWF-SCHEDULED — Drift, verify and acceptance run on a schedule

A scheduled workflow MUST run a drift `tofu plan` for every root and `make verify` and the acceptance checks for the fleet daily, in no-reviewer environments, and record receipts. A non-empty drift plan or a failed verify MUST fail the run so GitHub notifies the operator.

#### Scenario: Drift found

- **WHEN** a provider resource was changed in the console
- **THEN** the daily run fails and its receipt names the root

### Requirement: REQ-OPSWF-CLOUD-SESSION — The cloud session operates through Git only

The Claude cloud environment MUST attach the ops and public repositories, define no environment variables or secrets, use a limited network allowlist, and install toolchains with `scripts/cloud-env-setup.sh` from the public repository. The documented path MUST work with branch pushes and pull requests alone; `workflow_dispatch` from the cloud session MAY be used only for read-only operations and only if verified.

#### Scenario: Dispatch not permitted

- **WHEN** the cloud session's GitHub proxy refuses `gh workflow run`
- **THEN** the session opens a pull request with a request file and the operation still runs

### Requirement: REQ-OPSWF-RECEIPTS — Every run leaves a readable receipt

Each run MUST append a receipt (request ID, operation, targets, public repository SHA, ops commit, environment, approver, run URL, result) to the `ops-receipts` branch. Receipts MUST contain no secret values and no token-bearing URLs.

#### Scenario: Cloud session checks a result

- **WHEN** a cloud session needs the outcome of a merged request
- **THEN** it reads the receipt from `ops-receipts` without needing Actions API access
