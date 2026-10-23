# OPS-1792678016174902: Executable Path A recovery

## Objective

Execute UpCloud replacement recovery and safely continue after interruption.

## Ownership

Recovery lane: new scripts/recovery*.py, scripts/restore.sh, new recovery tests,
and this task/change. Primary integration lane: Makefile, runbooks and subtree
guidance. No live inputs or infrastructure mutation during source implementation.

## Execution

- [x] OPS-1792678266947663 Execute private recovery manifest admission and durable interrupted-operation reconciliation with regression coverage #feature !high @item:OPS-1792678016174902
- [x] OPS-1792678267794418 Provision and reconcile exact UpCloud replacement resources through reviewed canonical Terraform with lost-response tests #feature !high @item:OPS-1792678016174902
- [ ] OPS-1792678268575909 Run authenticated bootstrap ownership full deployment and device acceptance with resumed positive workflow tests #feature !high @item:OPS-1792678016174902
- [ ] OPS-1792678269304356 Integrate canonical operator entrypoint and verify complete source through independent review PR and main CI #feature !high @item:OPS-1792678016174902

## Verification

Dedicated unit and subprocess interruption tests, task validation, make check,
independent source/security review, protected PR and main CI. Live provider, guest
and client acceptance are outside this source-only delivery and remain unclaimed.
