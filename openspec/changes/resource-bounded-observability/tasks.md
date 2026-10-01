# MON-1790835036464962: Deliver resource-bounded monitoring without dedicated VPS nodes

## Objective

Run affordable, bounded metrics and independently supervised alerts on existing capacity, with positive live acceptance and no additional recurring infrastructure purchases. Uptime Kuma is the approved observer choice; its candidate existing host still requires admission. Planning does not complete any execution step or authorize unrelated host changes.

## Ownership

One serialized implementation lane owns `scripts/observability-*`, `contract/observability*`, `secrets/schema.json`, secret validators/coverage/examples, Make includes, and affected `vpnd/` callers. Runtime work owns `ansible/roles/observability_control_plane/`, `ansible/roles/observability_agent/`, affected deadman/shared-nginx integration, and corresponding tests/snapshots. Update the nearest role/subtree guidance when behavior changes. Terraform roots are not modified by this design. Preserve unrelated work and old task evidence.

Parallel implementation ownership: the integration lane owns the shared contracts, scripts, secret schema, Make, fixtures, runbooks and task tracking above. The bounded-runtime lane exclusively owns `ansible/roles/observability_control_plane/`, `ansible/roles/observability_agent/` and their role-specific unit tests, including `tests/unit/test_observability_telegram_delivery.py`. The observer lane exclusively owns the new `ansible/roles/observability_kuma/`, `ansible/playbooks/observability-kuma.yml`, and new `tests/unit/test_observability_kuma*.py` / `test_observability_push*.py` tests. Shared files and cross-lane inputs are serialized through the integration lane. Workers do not commit or perform live actions. The observer is not a VPN node; preserve the existing host's deployment ownership and unrelated workloads.

Observer implementation ownership has returned to the integration lane after
its runtime/test handoff. The bounded-runtime lane additionally owns authority
snapshot, generation and protocol-adapter integration regressions; shared
historical dead-man test migration remains in the integration lane.

The approved sender-replacement increment keeps that separation: the bounded-runtime
lane owns the agent role, its tests, and the control-plane cohosting runtime
fixtures, plus the collector disk-guard changes needed to account for the
sender queue on a shared filesystem and their focused regressions. The integration lane owns active operator/staging callers, shared
render fixtures, snapshots and documentation. The callsite audit and security
review are read-only. The existing resource/WAL step now requires the equivalent
persistent-queue outage/restart proof from the actual pinned vmagent runtime;
its historical-sample assertion and resource ceilings are not relaxed.
The integration lane also owns the collector alert-rule and rule-test templates
and their alerting unit test for explicit sender delivery-loss reporting.

## Execution

- [x] MON-1790835427523974 Migrate observability inventory and secrets contracts to co-hosted capabilities and a typed Uptime Kuma observer; update scripts, Make and affected vpnd callers with positive and obsolete-input tests #feature !high @item:MON-1790835036464962
- [ ] MON-1790835428068030 Implement bounded co-hosted collector and agent slices, ingestion budgets and latched disk-reserve guard; test load, WAL recovery, overload and VPN isolation #feature !high @item:MON-1790835036464962
- [ ] MON-1790835428600254 Implement private-IP SAN mTLS ingress and safe shared-nginx ownership; test trusted ingestion, revocation, wrong SAN and unchanged public VPN listeners #feature !high @item:MON-1790835036464962
- [ ] MON-1790835429142513 Implement pinned private Uptime Kuma runtime and scoped node/pipeline push producers with real-relay canaries; test stale receipts, credential rotation, observer loss, encrypted backup and isolated restore #feature !high @item:MON-1790835036464962
- [ ] MON-1790835429687617 Integrate rules, honest client-evidence states and reversible monitoring-only rollback; update role guidance, runbooks and snapshots and pass full source gates #feature !high @item:MON-1790835036464962
- [ ] MON-1790835430228619 After exact-host and credential authorization, admit collector and independent observer capacity, configure Kuma push monitors and verify human notifications, VPN non-regression, observer recovery and safe cutover #feature !high @item:MON-1790835036464962

## Verification

Requirement-to-step mappings and exact gates are in verification.md. Run targeted unit tests and role scenarios first, then snapshots, `make check`, and `make task-check`. Run heavy local checks through `build-gate --`. Hosted CI requires separately authorized publication; live admission/drills require exact-host infrastructure authority and scoped credentials. Client-path proof remains separate from host and API evidence. No checkbox completes on fixtures, refusal-only behavior, or an unobserved command.
