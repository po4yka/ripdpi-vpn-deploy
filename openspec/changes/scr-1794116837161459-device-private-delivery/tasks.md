# SCR-1794116837161459: Issue a device privately when the fleet has no subscription publisher

## Objective

`make device-lifecycle` issues and refreshes a `ripdpi` or `singbox` device on a fleet without a subscription publisher through one private recipient artifact, and refuses an expiry it cannot enforce.

## Ownership

Single serialized lane. `scripts/device_lifecycle.py`, `scripts/device_lifecycle_io.py`, `tests/unit/test_device_lifecycle.py`, `tests/unit/test_device_lifecycle_io.py`, `docs/how-to/device-lifecycle.md`.

## Execution

- [x] SCR-1794117494014479 Allow publisher-less ripdpi and singbox issue and refresh through one private artifact in device_lifecycle, with unit tests #feature !high @item:SCR-1794116837161459
- [x] SCR-1794118002578495 Refuse expiry without a publisher, document private delivery and run make check #feature !high @item:SCR-1794116837161459

## Verification

- Local narrow checks: the device lifecycle and migration unit tests, `make docs-check`.
- Local gate: `make check`, because the change touches secrets handling.
- Remote: PR CI on the exact head SHA.
- Live: issuance of `personal-pixel-incy` on the production fleet, as a separately authorized step.
- [ ] SCR-1794157295397257 Adopt devices with operator inputs and stable AWG peer comparison #bug !high @item:SCR-1794116837161459
