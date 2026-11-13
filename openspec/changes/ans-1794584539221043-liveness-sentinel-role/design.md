# Design: liveness-sentinel role

## Context

The native sentinel probe starts `sing-box` and `xray` by bare name and finds AWG under `/opt/ripdpi-real-vps-awg-nat/toolchains/<digest>`. Family nodes publish `/usr/local/bin/xray` through `xray-runtime`, so a sentinel cannot share that path.

## Decisions

- **Tier research.** The role is measurement-only, opens no listener and must never converge on a family node, which is what the research tier and `allow_research_roles` enforce.
- **Role-owned prefix.** Engines live in `/opt/ripdpi-liveness-sentinel/bin`. The probe prefers that path through one `engine()` helper and falls back to PATH, so existing sentinels keep working.
- **Verify, then install.** Each engine is downloaded into a root-private staging directory, its archive digest is checked, the staged binary's version is checked, then it is renamed into place. The installed path is hashed and run again. A failure leaves the previous binary.
- **Idempotence by record.** `state/<engine>.json` stores the archive and binary digests; an unchanged converge downloads nothing and still re-hashes and runs the installed binary.
- **One pin file.** `contract/liveness-runtime-pins.json` holds versions, archive names and digests. Ansible reads it with `lookup('file')`; the disposable provisioner loads it as JSON. AWG commits stay in `real-vps-awg-nat` defaults, which both flows already read.
- **AWG through the shared installer.** The installer owns `/opt/ripdpi-real-vps-awg-nat/toolchains`, links `awg` commands into `/usr/local/bin` and requires a content-addressed correction directory under `/usr/local/libexec/ripdpi`. The role copies its own installer into the prefix and refuses to run beside the family `amneziawg` role.
- **Packages.** `state: present` only, so installed packages are not upgraded; AWG build prerequisites install only when AWG is enabled.
- **Live Node B.** Enabling the toggle changes nothing the no-public-listener promotion kind checks (split-hop egress on, every client transport off, empty provider listener contract).

## Risks

- The AWG path needs controller-side source bundles; Molecule cannot build them offline, so it skips AWG and the installer keeps its own tests.
- Disabling the toggle does not uninstall; nodes are disposable.
