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
| `plan`, `apply`, `destroy`, `dns` | `tofu-plan` | `tofu-apply` (encrypted saved plan, hash in approval summary) |
| `dry-run`, `deploy` | `deploy-check` (dry-run) | `deploy` (dry-run then deploy) |
| `verify`, `acceptance` | `deploy-check` | `deploy-check` |
| `rotate-credentials`, `issue-device`, `revoke-device` | validation only | `ops-secrets` |
| `tailnet-policy` | GitOps action test | `tailnet-policy` |
| `none` | validation only | nothing |

- Job skeleton (all credentialed jobs): checkout ops at the event commit; checkout public at the `upstream.lock` SHA after the ancestor check; `mise install` from the public `mise.toml`; join the Tailnet with the job's tag; for OpenTofu jobs, `tofu init` with `TF_PLUGIN_CACHE_DIR` then export `HTTPS_PROXY` to the egress proxy; run the public Make target with `.fleet.mk` including the ops `fleet.mk`; write the receipt.
- Concurrency: `tofu-state-<root>-<workspace>` for every state writer (W3 contract), `deploy-<env>` for deploy, rotate and issue jobs; `cancel-in-progress: false`. Jobs that write state check the `STATE_HOLD` variable first.
- Saved plans: `tofu plan -out` produces a plan encrypted by the W3 `plan` encryption; it is uploaded as a short-retention artifact, and its SHA-256 goes into the approval summary; the apply job downloads it, checks the hash and applies it.
- Once-only execution: the merge job lists request files added in the pushed range, skips any request ID that has a receipt, and processes the rest in file-name order.
- Secrets in CI: `ops-secrets` jobs run the existing Make targets (`rotate-credentials`, `issue-sub-token`, `device-lifecycle`, `issue-hysteria-ech` and peers) that edit SOPS documents in place, then push a branch and open a pull request with `GITHUB_TOKEN` (`contents: write`, `pull-requests: write` on that job only) that contains the encrypted diff and a `deploy` request. Rejected: pushing secrets straight to the default branch (bypasses review).
- Client artifacts: `scripts/encrypt-client-artifact.sh` encrypts each delivery file with `age -r <recipient>` and `--check` refuses non-age input; uploads use `retention-days: 3`. The recipient key is public and lives in the request.
- Receipts: a workflow with `contents: write` appends `receipts/<yyyy>/<request-id>.json` to the unprotected `ops-receipts` branch. Rejected: committing receipts to the default branch (would retrigger and needs protection bypass).
- Log hygiene: workflows live only in the private ops repository; public SHA checkout never runs public workflows; summaries list addresses only in the private PR.
- Cloud environment: name `vpn-ops`; repositories ops and public; network Limited with GitHub, `registry.opentofu.org`, `github.com` release downloads and package managers allowed for offline checks; no variables; setup script `bash ripdpi-vpn-deploy/scripts/cloud-env-setup.sh` (installs mise pins and `requirements.txt`, no credentials, no hooks). Because hooks do not run with two repositories, the cloud session runs `make check` or the narrow checks itself before pushing.

## Contracts and ownership

- Public repository: `scripts/validate-ops-request.py`, `tests/unit/test_validate_ops_request.py`, `scripts/encrypt-client-artifact.sh`, `tests/unit/test_encrypt_client_artifact.py`, `scripts/cloud-env-setup.sh`, `docs/how-to/ops-workflows.md`, `docs/how-to/deploy.md`, `.agents/skills/vpn-deploy` and `vpn-acceptance` CI notes, `Makefile` only if a wrapper target is needed (last in the shared lane).
- Ops repository: `.github/workflows/{pr-preview,merge-execute,scheduled,dispatch}.yml` pinned by action SHA, `requests/README.md`, branch protection, `ops-receipts` branch.

## Risks / Trade-offs

- Two approvals for issuance and rotation (merge of the encrypted PR and the deploy request) → slower but each step is reviewed; both are phone-friendly.
- `pull_request_target` misuse is a known GitHub risk → only default-branch code runs, PR files are read as data after validation, executable-config PRs go to reviewer environments.
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
