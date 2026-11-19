# MON-1794937115554282: Silence external coverage alert during transport deploys

## Objective

`make deploy` and the device-lifecycle `rotate-credentials` step place a finite coverage-only silence for the node under change on the collector's silence gateway, end it with a short tail on success or remove it at once on failure, and only warn when the silence cannot be managed.

## Ownership

`scripts/observability-operator.py`, new `scripts/deployment_silence.py`, `scripts/deploy-controller.py`, `scripts/device_lifecycle_io.py`, `Makefile` (`deploy` recipe), `tests/unit/` for these modules, `docs/how-to/deploy.md`, `docs/reference/observability-operations.md`. One writer; serialize Makefile edits with other open changes.

## Execution

- [x] MON-1794937362082306 Add maintenance_silence() to observability-operator.py and the coverage_silence context manager in scripts/deployment_silence.py with unit tests #feature @item:MON-1794937115554282
- [x] MON-1794937405270339 Wrap site.yml in deploy-controller deploy mode and the rotate-credentials goal in device_lifecycle_io; forward settings in Makefile; extend tests #feature @item:MON-1794937115554282
- [x] MON-1794937453064568 Document configuration and lifecycle in deploy how-to and observability operations reference; run docs-check and make check #feature @item:MON-1794937115554282

## Verification

Local: focused pytest for the new module and both wiring points, `make docs-check`, `make check`. Remote CI on the PR. Dry-run: `make dry-run` with silence configured creates no silence. Live: one authorized deploy or rotation on a Telegram-mode node with silence configured; the gateway audit shows create, tail create and main delete, and no coverage notification arrives. Staging, client and artifact categories do not apply.
