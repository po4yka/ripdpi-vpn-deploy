# SEC-1793428392418058: Align the RIPDPI bundle latency probe cadence with the standard artifact

## Objective

Every emitted client document, the standard sing-box artifact and the RIPDPI bundle alike, probes latency every 30 minutes, and the bundle contract examples that the client vendors carry that interval.

## Ownership

Primary: this repository. `scripts/client_payload.py`; `contract/ripdpi-bundle.payload-failover.json` and `contract/ripdpi-bundle.hysteria-port-hopping.json`; `docs/reference/client-notes.md`; the `security/traffic-metadata-and-decoy-identity` delta spec. Paired client change: `po4yka/RIPDPI#DAT-1793428393229398` re-vendors the two contract files byte-identically.

## Execution

- [x] SEC-1793428478810526 Emit the 30-minute urltest interval for every format and refresh the contract examples #bug !high @item:SEC-1793428392418058
- [x] SEC-1793428480039653 Update the client notes and the prior change record then run the gates #bug !high @item:SEC-1793428392418058

## Verification

Local: `python3 -m pytest tests/unit/test_client_payload_recipient_boundaries.py tests/unit/test_emit_singbox_roundtrip.py`, `make docs-check`, `./taskctl validate`, `make task-federation PEER_ROOT=<RIPDPI checkout>`. Remote CI: the pull request's run at the exact head, then a `contract-sync` dispatch after both repositories merge. Dry-run, staging, live and client gates are not authorized by this change; no host is touched.
