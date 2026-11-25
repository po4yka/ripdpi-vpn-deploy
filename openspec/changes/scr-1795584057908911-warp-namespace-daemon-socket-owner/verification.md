---
task_id: SCR-1795584057908911
change: scr-1795584057908911-warp-namespace-daemon-socket-owner
commit_sha: null
local: passed
local_evidence: "2026-11-25 working tree on 5b575bd7c: `mise exec -- python3 -m pytest tests/unit/test_transport_egress_kernel.py` 78 passed, exit 0. `make -k -j 4 check`: every target passed (13005 unit tests) except `terraform-init`, which timed out on the provider registry and held back `validate` and `tf-test`; after a retry of the init, `make -k validate tf-test` exit 0. One independent security review of the patch: approve."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The socket-owner admission reads live sockets inside the namespace; a dry-run does not run it.
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Only the disposable staging profile enables the WARP outbound; no production profile runs the namespace check.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RDB-RELAY-OWNER | SCR-1795584146089592 | `mise exec -- python3 -m pytest tests/unit/test_transport_egress_kernel.py` | 78 passed: three admitted shapes, ten refused shapes; the staging rerun is still required |
| REQ-PROTO-RDB-RELAY-OWNER | SCR-1795584161332355 | `ansible/roles/transport-egress/CLAUDE.md` states the exception | done |
