# MON-1790835036464962: Deliver resource-bounded monitoring without dedicated VPS nodes

## Objective

Run affordable, bounded metrics and independently supervised alerts on existing capacity, with positive live acceptance and no additional recurring infrastructure purchases. Planning does not complete any execution step. Managed-service consent is pending; no enrollment or live action is authorized here.

## Ownership

One serialized implementation lane owns `scripts/observability-*`, `contract/observability*`, `secrets/schema.json`, secret validators/coverage/examples, Make includes, and affected `vpnd/` callers. Runtime work owns `ansible/roles/observability_control_plane/`, `ansible/roles/observability_agent/`, affected deadman/shared-nginx integration, and corresponding tests/snapshots. Update the nearest role/subtree guidance when behavior changes. Terraform roots are not modified by this design. Preserve unrelated work and old task evidence.

## Execution

- [ ] MON-1790835427523974 Migrate observability inventory and secrets contracts to co-hosted capabilities and typed managed checks; update scripts, Make and affected vpnd callers with positive and obsolete-input tests #feature !high @item:MON-1790835036464962
- [ ] MON-1790835428068030 Implement bounded co-hosted collector and agent slices, ingestion budgets and latched disk-reserve guard; test load, WAL recovery, overload and VPN isolation #feature !high @item:MON-1790835036464962
- [ ] MON-1790835428600254 Implement private-IP SAN mTLS ingress and safe shared-nginx ownership; test trusted ingestion, revocation, wrong SAN and unchanged public VPN listeners #feature !high @item:MON-1790835036464962
- [ ] MON-1790835429142513 Implement scoped direct node and pipeline heartbeats plus real-relay edit/send canaries; test stale receipts, redaction, endpoint failures and credential rotation #feature !high @item:MON-1790835036464962
- [ ] MON-1790835429687617 Integrate rules, honest client-evidence states and reversible monitoring-only rollback; update role guidance, runbooks and snapshots and pass full source gates #feature !high @item:MON-1790835036464962
- [ ] MON-1790835430228619 After explicit service and live authorization, admit existing capacity, enroll free managed checks and verify human notifications, VPN non-regression, failure recovery and safe cutover #feature !high @item:MON-1790835036464962

## Verification

Requirement-to-step mappings and exact gates are in verification.md. Run targeted unit tests and role scenarios first, then snapshots, `make check`, and `make task-check`. Run heavy local checks through `build-gate --`. Hosted CI requires separately authorized publication; live admission/drills require explicit infrastructure authority and service consent. Client-path proof remains separate from host and API evidence. No checkbox completes on fixtures, refusal-only behavior, or an unobserved command.
