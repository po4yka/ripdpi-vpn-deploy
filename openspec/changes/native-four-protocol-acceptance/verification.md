---
task_id: "TST-1791618356595983"
change: "native-four-protocol-acceptance"
commit_sha: "dee3439e3bd07ccd39ca21f33add14fd125fef06"
local: "passed"
local_evidence: "337 focused portable integration checks passed on the merged source (one existing SyntaxWarning). Both real separate-session scope cleanup cases passed locally. Full build-gate -- mise exec -- make check passed at 3d01cb1171e964bf85e7368c2fdb882b12f9fb7d: 7498 portable tests, 63 Bats and 320 vpnd tests plus static/schema/policy gates. The later full local repeat remained queued and was cancelled before execution; complete current source parity passed in CI."
remote_ci: "passed"
remote_ci_evidence: "CI run 38949485403 completed with all 90 jobs successful for implementation dee3439e3bd07ccd39ca21f33add14fd125fef06. Tested merge a1cee79b9766fc4a3a1bb1efb48a8ed0a70ec731 has that implementation and main 51aeb583fa95165f69b40970fa43cfc3226c778d as parents. The separate REALITY target validation workflow 38949485558 also passed."
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "isolated native source acceptance owns this change; fleet rehearsal requires separate authorization"
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "passed"
client_evidence: "34 actual isolated Linux native cases passed without skips: completion 17, lifecycle 6, hopping 2 and compensation 9. Real admitted Xray, Hysteria and both AWG source pairs exercised authenticated consuming clients, refusal, upgrade, retirement and recovery, including coupled frontend/gateway runtime rollback. No physical-device or fleet acceptance is claimed."
artifact: "passed"
artifact_evidence: "Run 38949485403 artifact native-four-transport-evidence/result.json records tested merge a1cee79b9766fc4a3a1bb1efb48a8ed0a70ec731, eight engine digests, all 34 passed cases, success=true, cleanup=true and empty cleanup_differences. The separate CI step removed and confirmed absence of the exact owned container. Only redacted JSON was uploaded. The owned local diagnostic container also matched its initial inventory and was removed."
---

# Verification

The complete selected runner passed against the exact implementation merged
with its recorded base, including the coupled gateway rollback and REALITY
validation changes. Subsequent task closure commits contain task/spec metadata
only. Native evidence covers isolated source and consuming clients; provider,
physical-device and live-fleet acceptance remain outside this task.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-NATIVE-COMPLETION | TST-1791618369402905 | CI run 38949485403, completion: 17 passed. Real HTTPS byte completion, TCP/UDP/DNS, wrong credentials/TLS, primary/alternate XHTTP delivery, two-instance binding and dual-stack AWG. | passed |
| REQ-PROTO-NATIVE-LIFECYCLE | TST-1791618370981853 | Same run, lifecycle: 6 passed. Exact AWG pair wire/warm adoption, changed unit sandbox and executable identity, unchanged retry, repeated two-to-one retirement, foreign tunnel/queue preservation and canonical nginx transaction coverage. | passed |
| REQ-PROTO-NATIVE-COMPENSATION | TST-1791618370981853 | Same run, compensation: 9 passed. Complete native upgrade/refusal/interruption recovery, coupled frontend/gateway rollback with exact live executable adoption, real nonempty Xray log rotation and authenticated recovery. Transient scopes reclaim separate-session Ansible workers; normal launcher exit and SIGKILL retain foreign workers. | passed |
| REQ-PROTO-NATIVE-HOPPING | TST-1791618372464891 | Same run, hopping: 2 passed. Both IP families traverse distinct range ports through complete canonical firewall renders, actual daemon lacks NET_ADMIN, foreign outbound UDP/table survive, and ordinary listener works after two removals. | passed |
| REQ-PROTO-NATIVE-HONESTY | TST-1791618373730661 | Portable runner refusal/privacy regressions passed; complete CI selected all 34 native cases with zero skips. Per-case, per-suite and final resource comparisons passed; engine/source identity remained unchanged; exact owned CI environment removal succeeded. | passed |
