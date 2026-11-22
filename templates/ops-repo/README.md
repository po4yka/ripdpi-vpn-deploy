# Ops repository

Private operator configuration for `po4yka/ripdpi-vpn-deploy`. It holds inventories, tfvars, profile overrides, SSH configuration, the SOPS recipient policy, SOPS-encrypted deployment documents, the catalog, plans and receipts. It holds no credential: no age identity, SSH private key, provider token, decrypted document, state or saved plan.

Contract: `docs/reference/ops-repository.md` in the public repository, pinned in `upstream.lock`.

## Use

1. Set `revision` in `upstream.lock` to the reviewed public commit.
2. In the public checkout, write an ignored `.fleet.mk` that contains one line: `include /absolute/path/to/this/checkout/fleet.mk`.
3. Run `scripts/validate-ops-repo.py <this checkout>` from the public checkout before every commit.

## Recovery order

1. Recover the operator age identity from the password manager.
2. Download and decrypt the sealed kit archive from the B2 recovery prefix.
3. Clone this repository and the public repository at the pinned revision.
4. Verify the selected account and resource before any live use.
