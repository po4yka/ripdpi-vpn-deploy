# ANS-1794214330785468: Host and refresh client routing lists on the subscription plane

## Objective

A delivery host refreshes client routing lists daily, admits them against private policy and serves them through a stable INCY Autorouting link.

## Ownership

Single serialized lane. `ansible/roles/subscription-host/`, `secrets/schema.json`, `secrets/prod.secrets.example.yaml`, `docs/reference/subscription-plane.md`, `tests/unit/test_routing_lists_refresh.py` and matching snapshots.

## Execution

- [x] ANS-1794218690815722 Refresh, admit and serve client routing lists from the subscription host #feature @item:ANS-1794214330785468

## Verification

- Local: `tests/unit/test_routing_lists_refresh.py`, `make snapshot-check`, `make check`.
- Remote: PR CI on the exact head SHA, including `subscription-host` Molecule.
- Dry-run, staging, live and client acceptance: separate authorized steps after this change merges.
