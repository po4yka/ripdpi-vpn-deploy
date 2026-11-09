# Change: Emit INCY import material from an issued device artifact

Task ID: `SCR-1794075997223882`

## Why

The owner wants to use INCY on a personal Android device (`personal-pixel-incy`) against all four deployed paths. The repository can emit only one P0 REALITY share URI (`client_payload.py --share-uri`). There is no emitter for P1 XHTTP or Hysteria2 links, and the delivery formats `ripdpi`, `singbox` and `native` produce nothing INCY imports for those paths. Building links by hand from decrypted secrets is error-prone: XHTTP paths, the Hysteria2 `<device>:<password>` auth and port-hopping syntax are easy to encode wrongly, and a hand-built link can silently drop a required field.

## What Changes

- New read-only Make target `emit-incy` that materializes the selected device through the existing canonical client payload and writes INCY share links for every enabled P0, P1 and Hysteria2 endpoint to a new owner-only file.
- The emitter refuses profiles with fields that the INCY link formats cannot carry, instead of omitting them.
- AmneziaWG delivery does not change: INCY imports the existing private `.conf`.
- No server, subscription publisher or device-lifecycle behavior changes. No new delivery format is published through `/sub/`.

## Capabilities

### New Capabilities

- `clients/incy-import-material`: exact, complete and refusing conversion of one device's materialized payload into INCY share links in a private file.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/client_payload.py` (link rendering beside `share_uri`), `Makefile` (`emit-incy`).
- Secrets: reads the same decrypted inputs as `emit-singbox`; output is access material and follows the private-file rules of the local operator kit.
- Docs: `docs/reference/make-targets.md` (generated), client delivery reference.
- Contract with INCY share-link formats as documented for INCY 3.9.x; Ferrum compatibility is proven only by device acceptance.
