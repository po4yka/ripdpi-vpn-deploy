# CIC-1795329226354380: Run plan, deploy, verify, rotate and issue from ops repository workflows

## Objective

Every operation runs from validated request files in the private ops repository: automatic previews for allowed fields, mutations once behind reviewers on merge, scheduled drift and verify, secrets created only in CI, client artifacts encrypted to the recipient, and a secretless Claude cloud environment that operates through Git alone.

## Ownership

Public: `scripts/validate-ops-request.py`, `scripts/encrypt-client-artifact.sh`, `scripts/cloud-env-setup.sh` and their tests, `docs/how-to/ops-workflows.md`, `docs/how-to/deploy.md`, `.agents/skills/vpn-deploy` and `vpn-acceptance` notes; `Makefile` last in the shared lane if needed. Ops repository: `.github/workflows/*`, `requests/`, `ops-receipts` branch, branch protection.

## Execution

- [ ] CIC-1795329330531652 Add the request file contract and validator with tests #feature !high @item:CIC-1795329226354380
- [ ] CIC-1795329344563256 Add the PR preview workflow with plan and dry-run summaries in no-reviewer environments #feature !high @item:CIC-1795329226354380
- [ ] CIC-1795329358597258 Add the merge execution workflow with read-only routing, protected request claims and interrupted-operation reconciliation, encrypted saved plans and receipts #feature !high @item:CIC-1795329226354380
- [ ] CIC-1795329376420274 Add scheduled drift, verify and acceptance and the offline preparation and separately approved activation for rotate, issue and revoke #feature !high @item:CIC-1795329226354380
- [ ] CIC-1795329399536234 Encrypt client configurations to the recipient age key and refuse plaintext artifacts, with tests #feature !high @item:CIC-1795329226354380
- [ ] CIC-1795329421913712 Add the cloud environment setup script and configure the Claude cloud environment with no secrets (authorized live step) #feature !high @item:CIC-1795329226354380
- [ ] CIC-1795329439874508 Run staging previews, a staging deploy and issue, and the workstation-off drill (authorized live step) #feature !high @item:CIC-1795329226354380

## Verification

Local: `python3 -m pytest tests/unit/test_validate_ops_request.py tests/unit/test_encrypt_client_artifact.py`, `make shellcheck`, `make docs-check`, `zizmor` on the ops workflows. Remote CI: public PR checks and ops repository workflow lint. Dry-run, staging, live and client (authorized): PR preview on a staging toggle, staging deploy request, staging issue to a test recipient key decrypted on a test client, drift and verify schedule receipts, and the workstation-off drill receipt.
