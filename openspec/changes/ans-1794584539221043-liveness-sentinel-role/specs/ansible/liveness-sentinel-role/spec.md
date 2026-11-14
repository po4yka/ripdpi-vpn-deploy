## ADDED Requirements

### Requirement: REQ-LSR-INSTALL — Engines install into a role-owned prefix only after verification

The role MUST install sing-box and Xray into `/opt/ripdpi-liveness-sentinel/bin` from root-private staging, verifying the archive digest and the staged binary version before an atomic rename, and MUST NOT write `/usr/local/bin/xray` or any other path another role owns.

#### Scenario: Digest or version does not match the pin

- **WHEN** an archive digest or a staged version differs from the pin
- **THEN** the converge fails, the previously installed binary is unchanged and staging is empty.

### Requirement: REQ-LSR-PINS — One canonical pin file

The role and `scripts/provision-disposable-liveness-runtime.py` MUST read engine versions and digests from `ansible/roles/liveness-sentinel/files/runtime-pins.json` and MUST NOT carry a second copy of a digest.

#### Scenario: A digest is duplicated

- **WHEN** an archive digest from the pin file appears in the role or the provisioner
- **THEN** the contract test fails.

### Requirement: REQ-LSR-PROBE — The native probe finds the role prefix

`scripts/vpn-protocol-liveness.py` MUST run an engine from the role prefix when it is executable there and otherwise fall back to the bare name.

#### Scenario: Prefix present or absent

- **WHEN** the prefix holds an executable engine, or does not
- **THEN** the probe uses that path, or the bare name.

### Requirement: REQ-LSR-OUTPUT — The installed pins are published

The role MUST publish a root-owned `/opt/ripdpi-liveness-sentinel/expected-runtime.json` holding the installed `sing_box` and `xray` versions, plus `awg` and `awg_toolchain` when the AWG toolchain is installed.

#### Scenario: Operator reads the pins

- **WHEN** the role converges
- **THEN** the file lists exactly the installed pins.

### Requirement: REQ-LSR-AWG — AWG uses the shared offline installer

When AWG is enabled the role MUST build the toolchain with `scripts/install-real-vps-awg-client-tools.py` from controller-side bundles under `/opt/ripdpi-real-vps-awg-nat/toolchains/<digest>`, with staging in a root-private directory.

#### Scenario: Inputs missing

- **WHEN** a bundle, vendor archive or digest is not supplied
- **THEN** the role refuses before changing the node.

### Requirement: REQ-LSR-INPUTS — The deploy controller admits the AWG inputs

The deployment controller's extra-vars validator MUST admit the six `liveness_sentinel_awg_*` keys only as one complete set, each path absolute and existing on the controller, each digest a lowercase SHA-256 equal to the file's actual digest, so `make deploy` can converge the role's AWG build.

#### Scenario: Incomplete or mismatched AWG inputs

- **WHEN** the extra-vars file omits one AWG input, gives a relative or missing path, or a digest that is malformed or differs from the file
- **THEN** the validator refuses the file before Ansible runs, and a complete verified set is accepted.

### Requirement: REQ-LSR-GATING — Research tier, no listener, live Node B only

The role MUST be classified research with toggle `vpn.enable_liveness_sentinel`, default false, MUST open no listener or service, and only `vpn-split-hop-egress-live` MUST enable it with `liveness-sentinel` in its allowlist, still admitted by the no-public-listener promotion kind.

#### Scenario: Profile gate

- **WHEN** `scripts/check-deploy-profile.py` and the profile contract tests run
- **THEN** they pass and the live Node B differs from the staging Node B by exactly the toggle and the allowlist entry.
