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

### Requirement: REQ-OPSWF-PREVIEW — Preview approved fields on trusted targets

For a same-repository PR, trusted default-branch code MUST plan and dry-run the affected targets and post a redacted summary. Only the typed changes permitted by `REQ-CIID-UNTRUSTED-INPUT` qualify for automatic credentialed previews. Any other change MUST wait for the operator to merge it and gets its first credentialed preview after merge.

#### Scenario: Toggle change

- **WHEN** a cloud session opens a pull request that changes a protocol toggle for one node
- **THEN** the PR shows a dry-run summary for that node within the same run and no secret appears in the log

### Requirement: REQ-OPSWF-EXECUTE-ONCE — Merged requests run once after the operator merges

Merged `plan` and `dry-run` requests MUST remain read-only. A mutation MUST claim its immutable request on the protected branch and verify that the operator merged it. Deploy MUST run dry-run first. Apply and destroy MUST use the approved encrypted plan. Only verified success permits skipping. A retry MUST reconcile the durable outcome or stop for operator review.

#### Scenario: Re-run of a merged workflow

- **WHEN** an operator re-runs the merge workflow for a request that already has a success receipt
- **THEN** the job exits without acting and records the skip

#### Scenario: Read-only request merged

- **WHEN** a plan or dry-run request merges with changes pending on a target
- **THEN** it reports the changes and invokes no mutation

#### Scenario: Runner stops after a side effect

- **WHEN** issuance commits its encrypted output or apply changes state and the runner stops before recording success
- **THEN** a retry reconciles the existing claim with the durable outcome and never repeats an unconfirmed mutation

#### Scenario: Plan changed after approval

- **WHEN** the saved plan hash differs from the approved one at apply time
- **THEN** apply stops and asks for a new plan

### Requirement: REQ-OPSWF-PREVIEWED-INPUTS — Mutations act only on previewed inputs

A mutation MUST act only when its operation, targets and inputs equal those of its merged pull-request preview. A request merged together with configuration that had no credentialed preview MUST NOT mutate; it needs a later request.

#### Scenario: Request merged with an unpreviewed address change

- **WHEN** a pull request changes a target address and adds a `deploy` request, and the operator merges it
- **THEN** the post-merge run previews the change, refuses the deploy and records that a new request is needed

### Requirement: REQ-OPSWF-SECRETS-IN-CI — Secrets are created and rotated only inside CI

An approved `ops-secrets` job MUST prepare encrypted changes offline and open a review PR with a follow-up deploy request. The job MUST keep plaintext, URLs and QR data out of logs, artifacts and Git. Only a separately approved deploy of the merged change MAY activate it on a node.

#### Scenario: Rotation

- **WHEN** a merged `rotate-credentials` request runs
- **THEN** a new pull request contains only changed `*.sops.yaml` files and a deploy request, and the job log contains no secret value
- **THEN** the preparation job makes no host connection and its stdout and stderr contain no delivery material

### Requirement: REQ-OPSWF-CLIENT-ENCRYPTION — Client configurations leave CI encrypted

An `issue-device` request MUST carry the recipient's age public key. Every client configuration, URL or QR code MUST be encrypted to that key before upload as an artifact with short retention. An upload step MUST refuse a file that is not an age ciphertext.

#### Scenario: Missing recipient key

- **WHEN** an `issue-device` request has no recipient key
- **THEN** validation fails and nothing is issued

#### Scenario: Plaintext artifact

- **WHEN** a step tries to upload a plaintext client configuration
- **THEN** `scripts/encrypt-client-artifact.sh --check` fails the job

### Requirement: REQ-OPSWF-SCHEDULED — Drift, verify and acceptance run on a schedule

A scheduled workflow MUST run a drift `tofu plan` for every root and `make verify` and the acceptance checks for the fleet daily, in the preview environments, and record receipts. A non-empty drift plan or a failed verify MUST fail the run so GitHub notifies the operator.

#### Scenario: Drift found

- **WHEN** a provider resource was changed in the console
- **THEN** the daily run fails and its receipt names the root

### Requirement: REQ-OPSWF-CLOUD-SESSION — The cloud session operates through Git only

The Claude cloud environment MUST attach the ops and public repositories, define no environment variables or secrets, use a limited network allowlist, and install toolchains with `scripts/cloud-env-setup.sh` from the public repository. The documented path MUST work with branch pushes and pull requests alone; `workflow_dispatch` from the cloud session MAY be used only for read-only operations and only if verified.

#### Scenario: Dispatch not permitted

- **WHEN** the cloud session's GitHub proxy refuses `gh workflow run`
- **THEN** the session opens a pull request with a request file and the operation still runs

### Requirement: REQ-OPSWF-RECEIPTS — Every run leaves a readable receipt

Each run MUST append a receipt (request ID, operation, targets, public repository SHA, ops commit, environment, approver, run URL, result) to the `ops-receipts` branch. Receipts MUST contain no secret values and no token-bearing URLs. Only the trusted executor MAY update execution state. The workflow MUST reject conflicting ID reuse and preserve records across concurrent updates.

#### Scenario: Cloud session checks a result

- **WHEN** a cloud session needs the outcome of a merged request
- **THEN** it reads the receipt from `ops-receipts` without needing Actions API access
