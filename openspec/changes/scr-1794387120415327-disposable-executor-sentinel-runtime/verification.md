---
task_id: SCR-1794387120415327
change: scr-1794387120415327-disposable-executor-sentinel-runtime
commit_sha: null
local: passed
local_evidence: "On base bf1cc67f: tests/unit/test_provision_disposable_liveness_runtime.py (8 passed), test_disposable_liveness_executor.py (27 passed; 11 fail without the umask change under umask 022), test_disposable_liveness_make.py, test_prepare_disposable_promotion_intent.py and test_disposable_promotion.py (168 passed in total), ruff on the new files and make docs-check passed."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The target changes only a local disposable Colima executor; no node, provider or Ansible run is involved.
staging: passed
staging_evidence: "make provision-disposable-liveness-runtime against the staging Node A executor (Colima profile vpn-liveness-split-hop-a, arm64) of ANS-1794231660855533 exited 0 twice from a fresh work directory and printed expected_runtime sing_box 1.14.3, xray 26.10.31, awg 1.0.20210914 and awg_toolchain 5520af8cc2807e7f375bf152241061d87544e2ef0a8993cc173f1433923a4a93; the second build reproduced the same toolchain digest."
live: not_applicable
live_evidence: Disposable staging tooling only; no production node uses the executor.
client: not_applicable
client_evidence: The executor's sentinel proof is evidence for ANS-1794231660855533.
artifact: not_applicable
artifact_evidence: No released artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DER-RUNTIME | SCR-1794387865903125 | `make provision-disposable-liveness-runtime` on the staging Node A executor printed all four runtime keys | Passed |
| REQ-DER-PINS | SCR-1794387865903125 | `tests/unit/test_provision_disposable_liveness_runtime.py::test_engine_pins_match_the_ci_pins_of_the_same_releases` and `::test_vendor_archive_is_deterministic_and_accepted_by_the_offline_builder` | Passed |
| REQ-DER-PREPARE | SCR-1794387865903125 | `tests/unit/test_disposable_liveness_executor.py` under umask 022 with a Colima fake that leaves the config mode to the umask | Passed |
