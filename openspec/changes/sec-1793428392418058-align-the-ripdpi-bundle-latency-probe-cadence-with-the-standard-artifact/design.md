## Context

`scripts/client_payload.py` builds one `auto` outbound for every format and selects `interval='5m' if o['format'] == 'ripdpi' else '30m'`. `tests/unit/test_client_payload_recipient_boundaries.py` compares the rendered bundle against the two contract examples, and `.github/workflows/contract-sync.yml` compares every file under `contract/` against the client's vendored copy on a weekly schedule and on dispatch. The client has no test that asserts the `urltest` interval value; its `RipdpiBundleContractTest` pins only the Hysteria hop interval.

## Goals / Non-Goals

- Goal: one probe cadence for every emitted format, with the contract examples and the client's vendored copies changed by the same single scalar.
- Non-goal: changing the probe URL, tolerance, the Hysteria hop interval, the bundle schema, or the operator-owned payload-failover contract.

## Decisions

- Remove the conditional rather than add a format parameter: the split existed only to keep `contract-sync` green, and no consumer wants a faster cadence. Rejected: a `--probe-interval` flag, which would add an operator input nobody asked for.
- Change the contract examples by editing the one scalar in place instead of regenerating them, so the diff proves that nothing else moved; the byte-compare tests confirm the emitter agrees.
- The delta spec adds `REQ-TMD-BUNDLE-CADENCE` to the same capability that `SEC-1793386547449444` introduces, and that change's `REQ-TMD-CLIENT-CADENCE` text is updated to name this task as the paired change, so the archived capability reads consistently once both changes land.

## Contracts and ownership

- Scripts: `scripts/client_payload.py` (`auto` outbound).
- Contract: `contract/ripdpi-bundle.payload-failover.json`, `contract/ripdpi-bundle.hysteria-port-hopping.json`; the client vendors both under `core/data/src/test/resources/contract/` in `po4yka/RIPDPI#DAT-1793428393229398`.
- Documentation: `docs/reference/client-notes.md`; the `SEC-1793386547449444` proposal, design and delta spec.
- No Terraform, Ansible, secrets, vpnd or configuration contract.

## Risks / Trade-offs

- `contract-sync` is red between the first and the second merge → merge the client re-vendor first or together, then dispatch `contract-sync` on the deployer and confirm it passes.
- Already-issued bundles keep probing every five minutes until re-emitted → the recipient page delivers a fresh bundle on the next fetch; no revocation is needed.

## Migration Plan

Forward: merge `po4yka/RIPDPI#DAT-1793428393229398`, then this change; dispatch `contract-sync`. Rollback: revert both commits in the opposite order. No provider, schema or secrets migration.
