# SCR-1791618073850409: Build and validate upgraded AmneziaWG sources locally

## Objective

Deliver the complete local source-candidate capability defined by the revised
specification. The owner explicitly excluded external infrastructure on 2026-10-15.
Production defaults and physical client safe floors remain unchanged.

## Ownership

- tests/integration/awg_source_candidate/sources.json
- scripts/test-awg-source-candidate.py
- tests/integration/awg_source_candidate/
- tests/unit/test_awg_source_candidate.py
- Makefile, .gitignore, scripts/CLAUDE.md, tests/CLAUDE.md, docs/TESTING.md, docs/AWG-COHORTS.md
- This change's planning and portfolio artifacts; one serialized writer.

## Execution

- [x] SCR-1791618078367215 Bind exact candidate and control source pairs and toolchain without promoting production defaults #feature @item:SCR-1791618073850409
- [x] SCR-1791618079169597 Deliver local real candidate builds and unchanged-wire authenticated interoperability #feature @item:SCR-1791618073850409
- [x] SCR-1791618080142425 Prove local warm pair and unit adoption failure compensation and unrelated tunnel preservation #feature @item:SCR-1791618073850409
- [ ] SCR-1791618081446678 Complete disconnected local source gates and document excluded physical and fleet claims #feature @item:SCR-1791618073850409

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_awg_source_candidate.py tests/unit/test_amneziawg_source_pins.py tests/unit/test_amneziawg_version_floor.py`
- `build-gate -- make test-awg-source-candidate`
- `make snapshot-check`
- `build-gate -- make check`

No unavailable native host, selected skip, physical-client claim or mocked
binary can satisfy the local source-candidate target. The broader native suite
and the physical/48-hour external procedure are outside this revised task.
