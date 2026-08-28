# OPS-1787496414433523: Harden deploy-path integrity: guards, rollback, rotation

## Objective

The canonical deploy path enforces its own guarantees on every invocation shape: guards run under any tag scope, deploys cannot race first-boot, renderer inputs fail closed at plan time, rollback and rotation keep their restore points consistent, failed probes clean up after themselves, and maintenance gates are deterministic regardless of host configuration or locale.

## Ownership

- The primary agent owns ansible/playbooks/{site,smoke-test,os-maintenance,rotate-credentials,rollback-xray}.yml, scripts/wait-cloud-init.sh, scripts/render-inventory.sh, Makefile deploy/dry-run targets, terraform/providers/*/variables.tf (allowlist validation only), ansible/group_vars/all.yml toggle section, and the new pytest coverage under tests/unit.
- Serialized shared-file lane: Makefile and group_vars/all.yml are edited by this change exclusively within this branch session.

## Execution

- [x] OPS-1787496118906514 Add tags: [always] to the secrets assert, role-tiers include_vars, research-tier guard, exception-tier guard, and listener-contract pre_tasks in site.yml #bug !high @item:OPS-1787496414433523
- [x] OPS-1787496118906556 Gate deploy and dry-run through one immutable canonical-inventory selection and strict transport for bounded bootstrap readiness, convergence and source parity #bug !high @item:OPS-1787496414433523
- [x] OPS-1787496118906208 Bound the remote cloud-init wait phase with a retry loop symmetric to the SSH phase and distinguish cloud-init error state from missing marker in the failure message #bug !high @item:OPS-1787496414433523
- [x] OPS-1787496118906369 Validate each COHORTS slug against the known group_vars/vpn-*.yml set during inventory rendering, failing loudly on unknown values #bug !high @item:OPS-1787496414433523
- [ ] OPS-1787496118906156 Reject an empty SSH allowlist at plan time: add a Terraform validation block requiring at least one CIDR and a matching site.yml assert mirroring the listener-contract guards #bug !high @item:OPS-1787496414433523
- [x] OPS-1787496118906901 Abort inventory rendering on duplicate host aliases across HOSTS pairs (or namespace aliases while keeping server_hostname as a host var) #bug !low @item:OPS-1787496414433523
- [ ] OPS-1787496118906340 Copy /etc/xray/config.json to config.json.prev in rotate-credentials before the template write, matching the xray role change-detection contract #bug !high @item:OPS-1787496414433523
- [ ] OPS-1787496118906432 Reorder rollback-xray to validate the target release binary against the current config before touching /opt/xray/current, and refuse a rollback to the currently pinned version #bug !high @item:OPS-1787496414433523
- [ ] OPS-1787496118906646 Wrap smoke-test per-protocol blocks in block/rescue/always stopping transient units and removing /run/vpn-smoketest on failure paths #bug !high @item:OPS-1787496414433523
- [ ] OPS-1787496118906956 Drop the externally managed management-plane unit from the unconditional os-maintenance is-active base list (gate it on a fact/toggle or remove) #bug !low @item:OPS-1787496414433523
- [ ] OPS-1787496118906821 Align every playbook inline enable_* default with group_vars/all.yml (hysteria/amneziawg true, nginx_xhttp true uniformly); add a pytest parity check over playbooks vs all.yml #bug !low @item:OPS-1787496414433523
- [ ] OPS-1787496118906614 Run the apt dist-upgrade simulation under LC_ALL=C so the residual-backlog assertion is locale-independent #bug !low @item:OPS-1787496414433523
- [ ] OPS-1787496118906731 Declare enable_cascade_ingress/enable_cascade_egress (default false) in group_vars/all.yml alongside the other toggles with a governance pointer comment #chore !low @item:OPS-1787496414433523
- [ ] OPS-1787496118907122 Extend tests/unit with named cases: tagged-guard execution, renderer slug/collision rejection, rollback ordering, rotation .prev creation, toggle-default parity; then make ci-fast and make validate #test !high @item:OPS-1787496414433523

## Verification

Use the exact gates and evidence categories in `verification.md`.
