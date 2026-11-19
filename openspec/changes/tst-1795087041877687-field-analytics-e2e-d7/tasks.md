# TST-1795087041877687: Accept field analytics end to end on staging with a client

## Objective

On a staging node and a Pixel or emulator, blocking one protocol with DROP or RST shows: the app classifies the stage, the report is ingested, the alert fires, the bundle marks the endpoint degraded and the client fails over.

## Ownership

One operator-authorized runner owns the staging node block and the client device for the run. No source files are edited besides the how-to and verification file.

## Execution

- [ ] TST-1795087071905692 Write the staging acceptance how-to under docs/how-to/ with the DROP and RST block and unblock commands and the observation checklist #feature @item:TST-1795087041877687
- [ ] TST-1795087099844740 Run the DROP case on the staging node with the client and record classification, ingest, alert, bundle and failover evidence #feature @item:TST-1795087041877687
- [ ] TST-1795087126099499 Run the RST case and record the same evidence #feature @item:TST-1795087041877687
- [ ] TST-1795087151868733 Remove the block, confirm recovery and record the final node and client state in verification.md #feature @item:TST-1795087041877687

## Verification

Staging: the recorded DROP and RST runs. Client: the Pixel or emulator run with the RIPDPI build under test. Local: `make docs-check`. Remote CI on the pull request.
