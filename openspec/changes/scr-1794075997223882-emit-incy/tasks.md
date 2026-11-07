# SCR-1794075997223882: Emit INCY import material from an issued device artifact

## Objective

`make emit-incy CLIENT=<device> OUTPUT=<path>` writes exact INCY share links for every enabled P0, P1 and Hysteria2 endpoint of one device to a new owner-only file, and refuses profiles whose fields the links cannot carry.

## Ownership

Single serialized lane. `scripts/client_payload.py`, `scripts/emit-singbox.sh`, `Makefile` (`emit-incy`), the matching `tests/unit/` share-link test file, the client delivery reference page and generated `docs/reference/make-targets.md`.

## Execution

- [ ] SCR-1794076666760854 Render INCY P0, P1 and Hysteria2 links from the ripdpi payload with refusals in client_payload.py, with literal-link unit tests #feature !high @item:SCR-1794075997223882
- [ ] SCR-1794077170024733 Add emit-singbox --incy-links and make emit-incy with owner-only output and overwrite refusal, with tests #feature !high @item:SCR-1794075997223882
- [ ] SCR-1794077673855163 Document INCY delivery in the client reference, regenerate make-targets and run make check #feature !high @item:SCR-1794075997223882

## Verification

- Local narrow checks: the matching `pytest` file, `make shellcheck`, `make docs-check`.
- Local gate: `make check`, because the change touches secrets handling.
- Remote: PR CI on the exact head SHA.
- Client: import of the emitted links into INCY on the owner's Android device with authenticated traffic and tunnel DNS on every path, as a separately authorized step.
- Dry-run, staging and live: not applicable; the change does not touch hosts.
