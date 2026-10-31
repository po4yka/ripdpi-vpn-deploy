---
task_id: SEC-1793428392418058
change: sec-1793428392418058-align-the-ripdpi-bundle-latency-probe-cadence-with-the-standard-artifact
commit_sha: null
local: passed
local_evidence: python3 -m pytest tests/unit/test_client_payload_recipient_boundaries.py tests/unit/test_emit_singbox_roundtrip.py (117 passed), make docs-check, ./taskctl validate, make task-federation PEER_ROOT=<RIPDPI checkout> (245 tasks valid), and every pre-commit hook on the commit passed.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Source, contract example and documentation change only; no private deployment plan is authorized.
staging: not_applicable
staging_evidence: No staging host is authorized for this change.
live: not_applicable
live_evidence: No provider, credential or live runtime mutation is included.
client: required
client_evidence: The client re-vendors both files byte-identically in po4yka/RIPDPI#DAT-1793428393229398; its unit tests and the deployer contract-sync dispatch after both merges remain to be recorded.
artifact: passed
artifact_evidence: The two contract example diffs change only the auto outbound interval scalar from 5m to 30m and are reviewed in the pull request diff.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TMD-CLIENT-CADENCE | SEC-1793428478810526 | Byte-compare tests in `tests/unit/test_client_payload_recipient_boundaries.py` against the updated contract examples; sing-box round-trip interval test | Passed locally (117 passed); remote CI pending |
| REQ-TMD-CLIENT-CADENCE | SEC-1793428480039653 | `make docs-check`, `./taskctl validate`, `make task-federation PEER_ROOT=<RIPDPI checkout>` | Passed locally; `contract-sync` dispatch pending until both repositories merge |
