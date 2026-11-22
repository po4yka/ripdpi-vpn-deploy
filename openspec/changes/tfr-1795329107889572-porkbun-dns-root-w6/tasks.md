# TFR-1795329107889572: Manage Porkbun DNS with a pinned OpenTofu root

## Objective

DNS records of the fleet's managed Porkbun domains are OpenTofu-managed with a vetted pinned provider, encrypted B2 state, a scope policy and API keys limited per domain, permission and egress address; existing records are adopted with a no-op plan.

## Ownership

New `terraform/dns/porkbun/**`, `terraform/policy/porkbun_scope*.rego`, `scripts/porkbun-import-blocks.py`, `tests/unit/test_porkbun_import_blocks.py`, `docs/how-to/dns.md`. Changed `Makefile` loops (after W5), `docs/reference/testing.md`, `terraform/CLAUDE.md`. Ops repository: tfvars and backend file.

## Execution

- [ ] TFR-1795329159424429 Vet and pin the Porkbun provider with lock-file hashes and record the vetting result #feature !high @item:TFR-1795329107889572
- [ ] TFR-1795329172302386 Add the Porkbun DNS root with encrypted B2 state, mock_provider tests, scope policy and the import-block script #feature !high @item:TFR-1795329107889572
- [ ] TFR-1795329184961660 Enable API access per managed domain, scope the keys and adopt existing records with a no-op plan (authorized live step) #feature !high @item:TFR-1795329107889572

## Verification

Local: `make tf-test`, `make tf-policy-verify`, `python3 -m pytest tests/unit/test_porkbun_import_blocks.py`, `make validate`. Remote CI: PR checks. Live (authorized): key scope receipt, off-egress call negative, no-op adoption plan and import apply receipts per domain.
