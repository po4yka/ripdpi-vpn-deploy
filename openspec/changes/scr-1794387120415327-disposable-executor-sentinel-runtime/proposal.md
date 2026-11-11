# Change: Provision the disposable liveness executor with sentinel runtimes

Task ID: `SCR-1794387120415327`

## Why

The first deploy of a fresh `device-full-staging` node requires a `disposable-staging-intent` whose single sentinel proves all four profiles, including `p2-amneziawg`. The sentinel runner verifies pinned sing-box and Xray on PATH and the immutable source-built AWG toolchain beneath `/opt/ripdpi-real-vps-awg-nat/toolchains/<source-input-digest>`. `make prepare-disposable-liveness` only creates an empty Colima VM, and the documentation calls runtime installation "a separate authorized action" without a supported command for this executor. Observed during `ANS-1794231660855533`: the staging Node A intent could not name a valid `expected_runtime`, and `prepare-disposable-liveness` itself failed because Colima 0.10 writes the profile config with the caller's umask while the executor contract requires an owner-only file.

## What Changes

- New `make provision-disposable-liveness-runtime EXECUTOR_MANIFEST=… RUNTIME_WORK_DIR=…` (`scripts/provision-disposable-liveness-runtime.py`): verifies the live executor manifest, installs the `real-vps-awg-nat` sentinel packages plus `golang-1.24-go`, installs sing-box and Xray for the executor architecture from release archives pinned by version and SHA-256, builds the AWG toolchain offline through the canonical `install-real-vps-awg-client-tools.py` from bundles of the role's pinned commits and an operator-made `vendor/` archive, and prints the `expected_runtime` block.
- `prepare-disposable-liveness` starts Colima under umask 077.
- The disposable onboarding reference and the deploy how-to name the new step.

## Capabilities

### New Capabilities

- `operations/disposable-executor-runtime`: a supported, pinned way to give the disposable executor the runtimes its sentinel verifies.

### Modified Capabilities

- None.

## Impact

- Scripts: new provisioner; one-line umask change in `disposable_liveness_executor.py`.
- Make: one new disposable-liveness goal with its own allowed command variables.
- Tests: provisioner boundaries, engine pins against the CI pins, vendor archive accepted by the real offline builder; the executor test fake now leaves the config mode to the umask.
- Docs: `docs/reference/protocol-liveness.md`, `docs/how-to/deploy.md`, generated `docs/reference/make-targets.md`.
- No Ansible role, Terraform, secrets schema or client contract change. The executor gains no credentials.
