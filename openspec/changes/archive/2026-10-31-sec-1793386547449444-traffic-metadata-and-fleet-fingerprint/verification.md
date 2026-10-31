---
task_id: SEC-1793386547449444
change: sec-1793386547449444-traffic-metadata-and-fleet-fingerprint
commit_sha: "61c0988342f38b5138273de39dfadb3e7dcf2b8c"
local: passed
local_evidence: Targeted pytest files for Xray, Hysteria unit, nginx public site, self-steal, REALITY validator and monitor, sing-box emission, client contracts, secrets schema and transport semantics passed; make snapshot-check reports 168 matching goldens; make docs-check and ansible-lint on the touched roles passed. make check -j 4 -k in the cloud container failed only on environment limits that reproduce on a clean main checkout - nginx -t cannot open an IPv6 listener in a kernel without IPv6, vpnd installer and bats sops tests refuse to run as root - and on the stale generated board, which was regenerated.
remote_ci: passed
remote_ci_evidence: "Pull request 426 passed CI run 41131429189 attempt 2 on head a0126fda2ff09a3bf4ed8f3901779b07347f5ec7: every job and the required-checks aggregate succeeded. Attempt 1 failed only contract-sync, because the client repository vendored a client-only fixture under its contract directory; client pull request po4yka/RIPDPI 693 moved that fixture out, and the re-run contract-sync job passed without any change to this head. The pull request was squash-merged as 61c0988342f38b5138273de39dfadb3e7dcf2b8c, whose tree is byte-identical to the tested head."
dry_run: not_applicable
dry_run_evidence: Source and test change only; no private deployment plan is authorized.
staging: not_applicable
staging_evidence: No staging host is authorized for this change.
live: not_applicable
live_evidence: No provider, credential or live runtime mutation is included.
client: not_applicable
client_evidence: The emitted sing-box document changes one scalar interval; the bundle schema is unchanged.
artifact: passed
artifact_evidence: Four refreshed snapshot goldens (xray config, hysteria unit, nginx site, watchdog probe) and the contract example interval are reviewed in the pull request diff.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TMD-NO-LEDGER | SEC-1793386902478660 | Rendered Xray and Hysteria unit tests plus refreshed snapshot goldens; passed locally and in CI run 41131429189 at the merged head | passed |
| REQ-TMD-OWNED-DECOY | SEC-1793386903380604 | nginx-xhttp task-contract tests, strict secrets validation on the example; passed locally and in CI run 41131429189 at the merged head | passed |
| REQ-TMD-PROBE-CONSISTENT | SEC-1793386903380604 | Rendered vhost test for intercepted upstream errors; passed locally and in CI run 41131429189 at the merged head | passed |
| REQ-TMD-REALITY-CONSISTENCY | SEC-1793386904380765 | Real TLS fixture tests for X25519 and DNS reasons; self-steal task test; passed locally and in CI run 41131429189 at the merged head | passed |
| REQ-TMD-CLIENT-CADENCE | SEC-1793386904380765 | sing-box round-trip test on the emitted interval; passed locally and in CI run 41131429189 at the merged head | passed |
