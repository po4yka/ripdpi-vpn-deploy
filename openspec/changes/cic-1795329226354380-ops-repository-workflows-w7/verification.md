---
task_id: CIC-1795329226354380
change: cic-1795329226354380-ops-repository-workflows-w7
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: Client artifacts are covered by the client gate; no release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPSWF-REQUEST | CIC-1795329330531652 | `pytest tests/unit/test_validate_ops_request.py` | planned |
| REQ-OPSWF-PREVIEW | CIC-1795329344563256 | staging toggle PR preview run | planned |
| REQ-OPSWF-EXECUTE-ONCE | CIC-1795329358597258 | Merge plan/dry-run with pending changes, conflicting claims, post-effect crash, resume and approved-plan mismatch tests | planned |
| REQ-OPSWF-PREVIEWED-INPUTS | CIC-1795329358597258 | merged request with unpreviewed address change refuses to deploy | planned |
| REQ-OPSWF-SECRETS-IN-CI | CIC-1795329376420274 | Offline issuance and rotation with host access denied, encrypted diff, stdout/stderr and artifact checks, followed by approved staging deployment | planned |
| REQ-OPSWF-CLIENT-ENCRYPTION | CIC-1795329399536234 | `pytest tests/unit/test_encrypt_client_artifact.py`; test client decrypt | planned |
| REQ-OPSWF-SCHEDULED | CIC-1795329376420274 | scheduled run receipts | planned |
| REQ-OPSWF-CLOUD-SESSION | CIC-1795329421913712 | cloud environment review and dispatch test result | planned |
| REQ-OPSWF-RECEIPTS | CIC-1795329439874508 | Branch protection, denied collaborator write and preserved concurrent attempt records | planned |

## Shared operational evidence ownership

| Source task | Operational owner | Requirement | Acceptance command | Evidence category | Source revision |
|---|---|---|---|---|---|
| SEC-1795328680299474 | CIC-1795329226354380 | REQ-CIID-SEPARATE | `make deploy ENV=staging` | staging | 5d7c0b583e42215aa0318599ee2b8d0dcd8278db |
| SEC-1795328680299474 | CIC-1795329226354380 | REQ-CIID-ENV-MATRIX | `python3 scripts/validate-ops-environments.py --root ripdpi-vpn-ops` | staging | 5d7c0b583e42215aa0318599ee2b8d0dcd8278db |
| SEC-1795328680299474 | CIC-1795329226354380 | REQ-CIID-BOOTSTRAP | `python3 scripts/validate-ops-environments.py --root ripdpi-vpn-ops` | staging | 5d7c0b583e42215aa0318599ee2b8d0dcd8278db |
| SEC-1795328680299474 | CIC-1795329226354380 | REQ-CIID-MERGE-GATE | `gh workflow run merge-gate-probe --repo po4yka/ripdpi-vpn-ops` | staging | 5d7c0b583e42215aa0318599ee2b8d0dcd8278db |
| SEC-1795328680299474 | CIC-1795329226354380 | REQ-CIID-MUTATION-TRIGGER | `make deploy ENV=staging` | staging | 5d7c0b583e42215aa0318599ee2b8d0dcd8278db |
| SEC-1795328680299474 | CIC-1795329226354380 | REQ-CIID-UNTRUSTED-INPUT | `python3 scripts/validate-ops-environments.py --root ripdpi-vpn-ops --pr BASE HEAD` | staging | 5d7c0b583e42215aa0318599ee2b8d0dcd8278db |
| SEC-1795328680299474 | CIC-1795329226354380 | REQ-CIID-LEAST-PRIVILEGE | `make plan ENV=staging` | staging | 5d7c0b583e42215aa0318599ee2b8d0dcd8278db |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-CONNECT-ONLY | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-TAILNET-ONLY | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-SECRETLESS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-HARDENED | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-FIXED-ADDRESS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-PROVIDER-PROOF | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-ALLOWLISTS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-BREAK-GLASS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
