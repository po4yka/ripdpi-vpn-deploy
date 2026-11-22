## Context

See `proposal.md`. Cloud-session research (2026-11-22, Claude Code cloud docs): the session's GitHub proxy keeps the real token outside the VM, allows branch pushes, rejects branch deletion, tag pushes and GraphQL (so `gh pr` fails), supports pull-request creation through the built-in tools, and does not document whether `gh workflow run` (REST) has `actions: write`. Environments have a network level (None, Limited with an allowlist and package-manager option, Full), environment variables, network secrets and a setup script; a session may attach several repositories, in which case repository hooks do not run. W3 defined writer serialization, W4 the environments and the untrusted-input rule, W5 the proxy.

## Goals / Non-Goals

- Goal: every operation the operator runs from the MacBook can run from the ops repository with phone approvals.
- Goal: the path works even if workflow dispatch from the cloud session is impossible.
- Non-goal: self-hosted runners; running anything credentialed in the public repository.

## Decisions

- Trigger model: request files plus pull requests. `pull_request_target` runs previews; `push` to the default branch runs new requests; `schedule` runs drift and verify; `workflow_dispatch` for operator and optional read-only cloud use. Rejected: `repository_dispatch` or `workflow_dispatch` as the only path (unverified permission); issue comments as commands (`gh issue` is GraphQL, and comments are weaker audit than merged files).
- Operation to environment map:

| Operation | PR preview | On merge |
|---|---|---|
| `plan` | `tofu-plan` | `tofu-plan` (plan only) |
| `apply`, `destroy`, `dns` (write) | `tofu-plan` | `tofu-apply` (apply the approved saved plan) |
| `dry-run` | `deploy-check` | `deploy-check` (dry-run only) |
| `deploy` | `deploy-check` (dry-run) | `deploy` (dry-run then deploy) |
| `verify`, `acceptance` | `deploy-check` | `deploy-check` |
| `rotate-credentials`, `issue-device`, `revoke-device` | validation only | `ops-secrets` |
| `tailnet-policy` | GitOps action test | `tailnet-policy` |
| `none` | validation only | nothing |

- Use the trusted workflow and the W4 classifier. For automatic PR previews, overlay only validated typed values on the base configuration. Run reviewer previews only for the approved PR head. For merged requests use the exact ops commit and validated public SHA. Load the job's minimum credentials, use W1's external input paths, and route backend initialization and normal provider requests through W5. Offline preparation needs no Tailnet access.
- Serialize deploys for the same environment. Every state writer uses the W3 backend lock, including during recovery. Scan merged requests for outstanding work after each push and on resume so a cancelled pending workflow cannot drop a request.
- Bind a saved plan's digest, operation, targets, input revision and public SHA to the approval. On merge, invalidate the preview if any effective input changed. Verify the approved digest immediately before applying the encrypted artifact.
- Serialize attempts for the same request ID. Resume an existing claim only after the previous worker has stopped. Claim a request by a compare-and-swap update on the protected execution branch before its first side effect. Bind the ID to the immutable request digest, operation and targets. Persist phase and outcome under that ID. A matching verified success skips execution. After interruption reconcile the operation's durable result (for example its encrypted preparation commit or applied state) before resuming. Reuse prepared material. If the outcome is ambiguous, halt for operator reconciliation. Reject ID reuse with different contents.
- Prepare rotation, revocation and issuance offline in `ops-secrets`. Persist the encrypted change under the request ID and open a PR containing it and a follow-up deploy request. Use generation and SOPS editing separately from `make rotate-credentials`, which reconciles live nodes. W7 owns splitting any combined issuer into offline preparation and approved activation. Route delivery bytes, including subscription URLs, directly into recipient encryption through private I/O. Reuse the recorded ciphertext on retry. Only the reviewed follow-up deploy may contact a node or activate credentials.
- Client artifacts: `scripts/encrypt-client-artifact.sh` encrypts each delivery file with `age -r <recipient>` and `--check` refuses non-age input; uploads use `retention-days: 3`. The recipient key is public and lives in the request.
- Keep execution state and per-attempt receipts on the protected `ops-receipts` branch. Allow writes only from a dedicated executor identity available to trusted default-branch jobs. Deny direct collaborator pushes, force-pushes and deletion. Use conditional ref updates so concurrent jobs preserve each other's records. Preview receipts and failed attempts cannot mark a request complete.
- Log hygiene: workflows live only in the private ops repository; public SHA checkout never runs public workflows; summaries list addresses only in the private PR.
- Cloud environment: name `vpn-ops`; repositories ops and public; network Limited with GitHub, `registry.opentofu.org`, `github.com` release downloads and package managers allowed for offline checks; no variables; setup script `bash ripdpi-vpn-deploy/scripts/cloud-env-setup.sh` (installs mise pins and `requirements.txt`, no credentials, no hooks). Because hooks do not run with two repositories, the cloud session runs `make check` or the narrow checks itself before pushing.

## Contracts and ownership

- Public repository: `scripts/validate-ops-request.py`, `tests/unit/test_validate_ops_request.py`, `scripts/encrypt-client-artifact.sh`, `tests/unit/test_encrypt_client_artifact.py`, `scripts/cloud-env-setup.sh`, `docs/how-to/ops-workflows.md`, `docs/how-to/deploy.md`, `.agents/skills/vpn-deploy` and `vpn-acceptance` CI notes, `Makefile` only if a wrapper target is needed (last in the shared lane).
- Ops repository: `.github/workflows/{pr-preview,merge-execute,scheduled,dispatch}.yml` pinned by action SHA, `requests/README.md`, branch protection, `ops-receipts` branch.

## Risks / Trade-offs

- Two approvals for issuance and rotation (merge of the encrypted PR and the deploy request) → slower but each step is reviewed; both are phone-friendly.
- Before releasing preview credentials, classify all changed paths and values against the W4 allowlist and bind reviewer approval to the immutable revision.
- GitHub outage stops everything → MacBook break-glass from W3 and W5.

## Migration Plan

1. Land public scripts, tests and docs (offline: unit tests, `make shellcheck`, `make docs-check`, `zizmor` on the ops workflow files via a fixture copy).
2. Authorized live steps: add workflows to the ops repository with Actions enabled and branch protection; run a `none` request, a plan-only request and a staging dry-run; then one staging deploy and one staging issue to a test recipient key; configure the cloud environment; run the epic's workstation-off drill.
3. Rollback: disable the ops workflows; the MacBook path still works against the same state and configuration.

## Open verification questions

1. Does the cloud session's GitHub proxy allow `gh workflow run` (REST `POST /actions/workflows/{id}/dispatches`) with a token that has `actions: write`? Test with a no-op workflow; the design does not depend on it.
2. Can the cloud session read workflow run status and logs through REST (`gh run view`), or only the `ops-receipts` branch?
3. Can the cloud session open pull requests in the ops repository whose head branch is in the same repository, so `pull_request_target` previews apply?
4. Do GitHub Mobile deployment-review approvals work for all four reviewer environments?
5. Does a two-repository cloud environment check out both repositories side by side so the setup script path resolves?
6. Are workflow run logs of a private repository visible to anyone outside the collaborator list (for example through Actions log retention or forks)? Confirm fork policy is "no forks" for the ops repository.
