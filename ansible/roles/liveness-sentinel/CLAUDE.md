# role: liveness-sentinel — pinned probe engines for a cloud sentinel

## Design decisions

**Measurement-only research role, no service and no listener** — it installs the pinned sing-box and Xray plus the immutable AWG client toolchain so a native Linux protocol-liveness sentinel can probe. `ansible/role-tiers.yml` classifies it `research` (toggle `vpn.enable_liveness_sentinel`) because it exists only to measure and must never reach a family profile; a host needs `allow_research_roles: [liveness-sentinel]`. The first consumer is the long-lived split-hop Node B (`group_vars/vpn-split-hop-egress-live.yml`), which stays listener-free.

**Role-owned prefix, never a PATH directory** — engines live in `/opt/ripdpi-liveness-sentinel/bin`. `scripts/vpn-protocol-liveness.py` (`ENGINE_BIN`) prefers that path and falls back to PATH for older sentinels. The role must never write `/usr/local/bin/xray`, which `xray-runtime` owns as a public symlink on fleet nodes.

**One pin file** — `contract/liveness-runtime-pins.json` holds engine versions, archive names and sha256 digests, the AWG repositories and the Go package. This role and `scripts/provision-disposable-liveness-runtime.py` both read it; never copy a digest elsewhere. AWG commits come from `real-vps-awg-nat` defaults.

**Verify, then install** — `tasks/engine.yml` downloads into a root-private `staging/` directory, checks the archive digest (`get_url` checksum), extracts one member, runs the staged binary for its version and only then renames it into place with an atomic `copy remote_src`. A failure leaves the previous binary. After install it re-hashes and runs the exact installed path. `state/<engine>.json` records archive and binary digests so an unchanged converge downloads nothing.

**AWG uses the shared offline installer** — controller-side bundles, vendor archive and digests are private extra vars (same as the `real-vps-awg-nat` sentinel mode). The installer verifies them before it builds and owns `/opt/ripdpi-real-vps-awg-nat/toolchains/<digest>`. It also links `awg`, `awg-quick` and `amneziawg-go` into `/usr/local/bin` and requires its correction directory at `/usr/local/libexec/ripdpi/awg-source-<digest>` (content-addressed); the role refuses to run beside the family `amneziawg` role for that reason.

**Operator output** — `/opt/ripdpi-liveness-sentinel/expected-runtime.json` holds `{awg, awg_toolchain, sing_box, xray}` (AWG keys only when AWG is installed). Fetch it after converge with `ansible <host> -b -m ansible.builtin.fetch -a 'src=/opt/ripdpi-liveness-sentinel/expected-runtime.json dest=<private dir>/ flat=yes'` and copy the values into the liveness configuration's `expected_runtime`.

## What's done well

- Prefix, staging and state are root-owned; staging is mode `0700` and emptied on every path.
- Packages use `state: present`, so installed packages are never upgraded.
- Molecule proves digest and version refusal keep the previous binary, and that a planted `/usr/local/bin/xray` link is untouched.

## Pitfalls

- Disabling the toggle does not uninstall anything; nodes are disposable, recreate instead.
- Molecule sets `liveness_sentinel_install_awg: false`; the AWG build needs real source bundles and is covered by the installer's own tests and the disposable flow.
- Check mode skips the install tasks, so a dry run cannot preview engine changes.
- Changing a pin means updating the version and every archive digest together in the JSON file; the disposable flow reads the same file.
