---
task_id: SCR-1793858662430806
change: scr-1793858662430806-self-steal-cert-renewal
commit_sha: pending
local: passed
local_evidence: "tests/unit/test_renew_self_steal_cert.py: 9 passed, including refusals without VPN_SECRETS_FILE or VULTR_API_KEY and a source-specific pending match. An end-to-end run of sops exec-env with the VULTR_API_KEY-only authority, then make renew-self-steal-cert through the decrypt/clean gate against the live P0 document, returned not-due with 88 days remaining and left no decrypted file. Earlier result: 6 passed, also with the macOS LibreSSL openssl first on PATH. make shellcheck and make docs-check passed. Against the live P0 document with real sops, the run returned not-due with 89 days remaining and wrote nothing. On an encrypted copy, with real sops and a stub lego, a due run produced an encrypted document carrying the issued pair, left the source unchanged, left no issued key and no temporary candidate on disk, and the second run returned awaiting-deploy."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request.
dry_run: not_applicable
dry_run_evidence: The change adds an operator-side tool; it does not change rendered deployment input.
staging: not_applicable
staging_evidence: No staging rollout is involved.
live: required
live_evidence: Pending installation of the daily operator job after merge.
client: not_applicable
client_evidence: The certificate content seen by clients does not change until a renewed document is deployed through the reviewed path.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-SSR-DUE-ONLY | SCR-1793859258666469 | Tests for not-due and awaiting-deploy; a live not-due run against the P0 document | passed |
| REQ-OPS-SSR-NEW-DOCUMENT | SCR-1793859258666469 | Tests for name, version and shared-host refusal and for a new document only; a real-sops run on an encrypted copy | passed |
