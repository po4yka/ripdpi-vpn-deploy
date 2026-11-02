---
task_id: XRY-1793635470456809
change: xhttp-payload-tcp-reserve
commit_sha: b25d6d94c7a466edd674df34e8cc4371721c4e95
local: passed
local_evidence: Targeted exporter/schema checks passed, 257 tests. The build-gate make -k -j4 check run passed its other gates but found a local parser-version mismatch and 56 unit failures on macOS (11205 passed, 45 subtests passed). Exact checksum-verified CI parser versions passed the liveness rerun. Six unit cases passed after using the direct pinned promtool binary and rerunning process cleanup alone. The other 50 passed on the exact source commit in isolated offline Linux arm64 with Python 3.12 and hash-pinned dependencies. Native OpenSSH and Bash failures also reproduced on clean main; the Linux task-history lookup passed. No assertions or runtime source were changed to obtain these results. Delivery-note follow-up passed make docs-check, 10 tests.
remote_ci: required
remote_ci_evidence: Run the selected checks on both PR heads.
dry_run: not_applicable
dry_run_evidence: Source and local test changes only.
staging: not_applicable
staging_evidence: No staging rollout is included.
live: not_applicable
live_evidence: No live host or credential action is included.
client: required
client_evidence: Paired source 2260e0b9e54eabe0c7ad7ae0a86086b5f76ef173 passed 285 native tests, 123 Kotlin tests, staticAnalysis, strict async Clippy, Miri and independent review. Three existing native peer tests stayed ignored. The later backup/share field-classification correction passed 16 owner tests; full coverage and hosted CI are tracked in the paired review task. Physical-device and filtered-network acceptance are outside this change.
artifact: passed
artifact_evidence: The formatted mixed emitted fixture matches the paired consumer byte for byte. Bundle schema validation passed; federation validation passed for 242 tasks.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-XHTTP-RECIPIENT-POOL | XRY-1793635898207050 | Exporter bounds and paired storage/runtime/native socket checks passed; paired hosted CI pending | Required |
| REQ-FAILOVER-TCP-RESERVE | XRY-1793635898207050 | Mixed fixture, exact payload verifier and paired Hysteria2-to-TCP selector checks passed; hosted CI pending | Required |
