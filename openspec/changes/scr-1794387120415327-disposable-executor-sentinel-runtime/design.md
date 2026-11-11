# Design: disposable executor sentinel runtimes

## Context

`scripts/vpn-protocol-liveness.py` compares the sentinel's observed runtime with `expected_runtime`: `sing-box version` and `xray version` from PATH, and for AWG a toolchain whose canonical manifest, tree and binary hashes it verifies under `/opt/ripdpi-real-vps-awg-nat/toolchains/<id>`. The persistent sentinel gets these through the `real-vps-awg-nat` role, which copies offline bundles and runs `install-real-vps-awg-client-tools.py`. The disposable executor is a Colima VM reached only through `colima ssh --profile <exact>`; Ansible does not target it.

## Decisions

- One operator command on the controller machine, not an Ansible play: the executor has no inventory entry, and every existing executor command already goes through `executor_command`. The command first loads the live executor manifest, so it refuses an expired or foreign profile.
- Single sources: the package list and AWG commit pins are read from the `real-vps-awg-nat` role; the offline build is the canonical installer, unchanged. Engine pins live in the provisioner, with a test that the amd64 digests and versions equal the CI pins and the local parser pins of the same releases. The arm64 digests come from the same upstream release metadata that matches those amd64 pins.
- The operator machine downloads and verifies every input. The executor builds AWG in the installer's network-less namespace, so the VM never fetches build inputs. Only apt packages come from the VM's distribution mirror, as on the persistent sentinel.
- `golang-1.24-go` is added because Ubuntu 24.04's default Go (1.22.2) is older than `amneziawg-go`'s `go.mod` floor and the installer runs with `GOTOOLCHAIN=local`.
- The vendor archive is deterministic (sorted members, zero owner and time), holds only `vendor/`, and is validated by the installer's own `validate_vendor` in tests.
- `prepare_executor` sets umask 077 around `colima start`: the executor contract keeps rejecting a group/other-readable config, and Colima 0.10 inherits the caller's umask.

## Alternatives rejected

- Run the `real-vps-awg-nat` sentinel tasks against the executor: they also manage the recurring evidence timer, lanes and echo/server groups that a one-shot executor does not have.
- Relax the toolchain check for disposable sentinels: `awg_toolchain` is part of the evaluated provenance and the four-profile staging promotion.
- Download engines inside the VM: the controller then could not verify digests before the bytes reach the executor.

## Rollback

Remove the target and script; executors prepared without it simply cannot pass an AWG sentinel, as before. The umask change has no effect on an already owner-only config.
