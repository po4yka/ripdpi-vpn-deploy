# Change: Accept field analytics end to end on staging with a client

Task ID: `TST-1795087041877687`

## Why

Unit and contract tests cannot show that the cross-repository chain works. Authenticated client traffic needs `client: passed` and staging evidence. Part of epic `EPC-1795085241910080`; blocked by D2 (`SEC-1795086333272606`), D4 (`SCR-1795086521848661`) and D5 (`MON-1795086646495369`), and by the RIPDPI client work R1 to R4.

## What Changes

- Add a staging acceptance procedure and run it with a Pixel or emulator: block one protocol with DROP and with RST, observe stage classification, ingest, alert, degraded bundle health and client failover.
- Record the evidence with the conventions of the `vpn-acceptance` skill.
- Counterpart RIPDPI work: R1 to R4 must be available in the tested app build; see design.md for the IDs.

## Capabilities

### New Capabilities

- `operations/field-analytics-e2e`: end-to-end acceptance of the field analytics chain.

### Modified Capabilities

- None.

## Impact

- Docs: a staging acceptance how-to under `docs/how-to/`.
- Evidence: the verification file; staging node and device are real infrastructure and need operator authorization at run time.
