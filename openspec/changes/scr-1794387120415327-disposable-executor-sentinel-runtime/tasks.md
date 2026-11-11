# SCR-1794387120415327: Provision the disposable liveness executor with sentinel runtimes

## Objective

The disposable liveness executor carries the pinned sing-box and Xray and the offline-built AWG toolchain that its four-profile staging sentinel verifies, installed by one Make target that prints the matching `expected_runtime`; executor preparation no longer depends on the operator's umask.

## Ownership

Single serialized lane. Scripts: `scripts/provision-disposable-liveness-runtime.py`, `scripts/disposable_liveness_executor.py`. Make: the `provision-disposable-liveness-runtime` goal. Tests: `tests/unit/test_provision_disposable_liveness_runtime.py`, `tests/unit/test_disposable_liveness_executor.py`. Docs: `docs/reference/protocol-liveness.md`, `docs/how-to/deploy.md`, generated `docs/reference/make-targets.md`.

## Execution

- [x] SCR-1794387865903125 Install pinned sentinel runtimes into the disposable executor through a Make target #feature !high @item:SCR-1794387120415327

## Verification

- Local narrow checks: the provisioner and executor unit tests, the disposable make and promotion tests, ruff on the new files, `make docs-check`.
- Live executor: `make provision-disposable-liveness-runtime` against the staging Node A executor of `ANS-1794231660855533`.
- Remote: PR CI on the exact head SHA.
