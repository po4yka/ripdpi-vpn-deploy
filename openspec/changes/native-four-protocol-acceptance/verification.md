---
task_id: "TST-1791618356595983"
change: "native-four-protocol-acceptance"
commit_sha: "ea5ba69a5518571c27d3bf9f09f13053be874e35"
local: "passed"
local_evidence: "337 focused portable integration checks passed on the merged tree (one existing SyntaxWarning). 76 focused runner, selector, cache and instruction checks passed on the implementation; both real separate-session scope cleanup cases passed locally. The full build-gate -- mise exec -- make check passed at 3d01cb1171e964bf85e7368c2fdb882b12f9fb7d: 7498 portable tests, 63 Bats and 320 vpnd tests plus static/schema/policy gates. Post-merge focused coverage passed 163 tests. The later full local repeat remained queued and was cancelled before execution; current complete source parity passed in CI."
remote_ci: "required"
remote_ci_evidence: "Prior-base evidence; integrated rerun after main 51aeb583fa95165f69b40970fa43cfc3226c778d is required. CI run 38937693541 completed with all 90 jobs successful for implementation ea5ba69a5518571c27d3bf9f09f13053be874e35. Tested merge d39a4ce67eb1b1c6f95362f0d8bfeabf599a1da2 has that implementation and main 5daffa6a630883c389257ef161f6c9663103c47c as parents."
dry_run: "not_applicable"
dry_run_evidence: "source-only capability; no controller or provider execution in this task"
staging: "not_applicable"
staging_evidence: "isolated native source acceptance owns this change; fleet rehearsal requires separate authorization"
live: "not_applicable"
live_evidence: "no production rollout is part of this source task"
client: "required"
client_evidence: "Prior-base evidence; integrated rerun after main 51aeb583fa95165f69b40970fa43cfc3226c778d is required. 34 actual isolated Linux native cases passed without skips: completion 17, lifecycle 6, hopping 2 and compensation 9. Real admitted Xray, Hysteria and both AWG source pairs exercised authenticated consuming clients, refusal, upgrade, retirement and recovery. No physical-device or fleet acceptance is claimed."
artifact: "required"
artifact_evidence: "Prior-base evidence; integrated rerun after main 51aeb583fa95165f69b40970fa43cfc3226c778d is required. Run 38937693541 artifact native-four-transport-evidence/result.json records tested merge d39a4ce67eb1b1c6f95362f0d8bfeabf599a1da2, eight engine digests, all 34 passed cases, success=true, cleanup=true and empty cleanup_differences. The separate CI step removed and confirmed absence of the exact owned container. Only redacted JSON was uploaded."
---

# Verification

The complete selected runner passed for the recorded implementation and its
previous base. Main subsequently advanced to
51aeb583fa95165f69b40970fa43cfc3226c778d with coupled gateway rollback and
REALITY validation changes. The merged tree requires a fresh complete CI run
before archival; the earlier positive evidence below is retained as history.
Native evidence covers isolated source and consuming clients; provider,
physical-device and live-fleet acceptance remain outside this task.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-NATIVE-COMPLETION | TST-1791618369402905 | CI run 38937693541, completion: 17 passed. Real HTTPS byte completion, TCP/UDP/DNS, wrong credentials/TLS, primary/alternate XHTTP delivery, two-instance binding and dual-stack AWG. | previous base passed; integrated rerun required |
| REQ-PROTO-NATIVE-LIFECYCLE | TST-1791618370981853 | Same run, lifecycle: 6 passed. Exact AWG pair wire/warm adoption, changed unit sandbox and executable identity, unchanged retry, repeated two-to-one retirement, foreign tunnel/queue preservation and canonical nginx transaction coverage. | previous base passed; integrated rerun required |
| REQ-PROTO-NATIVE-COMPENSATION | TST-1791618370981853 | Same run, compensation: 9 passed. Complete native upgrade/refusal/interruption recovery, real nonempty Xray log rotation and authenticated recovery. Transient scopes reclaim separate-session Ansible workers; normal launcher exit and SIGKILL retain foreign workers. | previous base passed; integrated rerun required |
| REQ-PROTO-NATIVE-HOPPING | TST-1791618372464891 | Same run, hopping: 2 passed. Both IP families traverse distinct range ports through complete canonical firewall renders, actual daemon lacks NET_ADMIN, foreign outbound UDP/table survive, and ordinary listener works after two removals. | previous base passed; integrated rerun required |
| REQ-PROTO-NATIVE-HONESTY | TST-1791618373730661 | Portable runner refusal/privacy regressions passed; complete CI selected all 34 native cases with zero skips. Per-case, per-suite and final resource comparisons passed; engine/source identity remained unchanged; exact owned CI environment removal succeeded. | previous base passed; integrated rerun required |
