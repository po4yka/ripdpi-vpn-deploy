# TFR-1795328481774241: Move OpenTofu state to an encrypted, locked object storage backend

## Objective

Every root encrypts state and saved plans on the client. Fleet provider roots store state in a versioned, object-locked Scaleway Object Storage bucket with scoped keys and serialized writers; all current local states are migrated exactly and can be restored from the MacBook without GitHub.

## Ownership

`terraform/**/versions.tf`, `scripts/terraform-env.sh`, `scripts/policy-plan.sh`, `scripts/backup-tf-state.sh`, `scripts/restore-tf-state.sh`, new `scripts/state-lock-probe.sh`, `tests/unit/test_state_lock_probe.py` and affected state-script tests, `Makefile` (after W2 in the shared lane), `docs/reference/secrets.md`, `docs/how-to/deploy.md`, `terraform/CLAUDE.md`. Ops repository: `config/backend/*.s3.tfbackend`.

## Execution

- [x] TFR-1795328555023000 Add the state and plan encryption block with an unencrypted migration fallback to every root #feature !high @item:TFR-1795328481774241
- [x] TFR-1795328567014606 Add the partial S3 backend on Scaleway Object Storage, workspace key layout and the shared backend lock for all writers #feature !high @item:TFR-1795328481774241
- [x] TFR-1795328578453594 Add the state backend lock probe for lock contention, release and reacquisition, checksums, versions and encrypted payloads with tests #feature !high @item:TFR-1795328481774241
- [x] TFR-1795328590452221 Create the bucket and bucket-scoped keys, then run the probe (authorized live step) #feature !high @item:TFR-1795328481774241
- [x] TFR-1795328602611143 Migrate each root with a verified backup and address, lineage and serial comparison (authorized live step) #feature !high @item:TFR-1795328481774241
- [x] TFR-1795328613654811 Enforce encryption, move backup and restore onto bucket versions, and document state break-glass #feature !high @item:TFR-1795328481774241

## Verification

Local: `python3 -m pytest tests/unit/test_state_lock_probe.py` and the state-script tests, `make tf-test`, `make validate`, `make shellcheck`. Remote CI: PR checks. Live (authorized): probe report on the real bucket; per-root migration receipts with address, lineage and serial equality and a no-change plan; one restore drill from a retained Scaleway version on the MacBook. No Ansible deploy or client change.
