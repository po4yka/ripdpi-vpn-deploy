# SEC-1787496881680472: Establish single-owner sshd configuration layers

## Objective

Every sshd setting on a managed node has exactly one owning file, cross-file duplication is a convergence failure rather than a silent shadow, validation evaluates the effective configuration, and SSH algorithm negotiation is pinned at the managed layer and asserted post-converge.

## Ownership

- The primary agent owns terraform/shared/cloud-init.yaml.tftpl, ansible/roles/baseline/{tasks/main.yml,templates/sshd_config.d-hardening.conf.j2}, ansible/playbooks/verify.yml, and the molecule coverage for baseline sshd behavior.
- Serialized shared-file lane: cloud-init.yaml.tftpl is edited exclusively within this change.

## Execution

- [x] SEC-1787496118906462 Reduce the cloud-init drop-in to boot-critical keys (Port, PasswordAuthentication/KbdInteractiveAuthentication/PermitRootLogin/PubkeyAuthentication off-on primitives) with an ownership header comment #bug !high @item:SEC-1787496881680472
- [x] SEC-1787496118906246 Make the managed 20- drop-in the sole owner of all tunable hardening directives with a matching ownership comment block #bug !high @item:SEC-1787496881680472
- [x] SEC-1787496118906968 Add a pre-write baseline task that parses both drop-ins and fails when any directive key appears in more than one file #bug !high @item:SEC-1787496881680472
- [x] SEC-1787496118907241 Switch the baseline template validation from fragment-only sshd -t to an effective-config check after assembly (sshd -T parse diff of the managed keys) #bug !high @item:SEC-1787496881680472
- [x] SEC-1787496118907162 Add a managed Ciphers/MACs/KexAlgorithms allowlist sized for the pinned Debian 13 / Ubuntu 24.04 images and assert the effective set in verify.yml next to the existing effective-config checks #bug !low @item:SEC-1787496881680472
- [x] SEC-1787496118907080 Run named source gates: baseline Molecule matrix on both distros, make ci-fast and make validate; the real SSH rehearsal is owned by SEC-1787916931540401 #test !high @item:SEC-1787496881680472

## Verification

Use the exact gates and evidence categories in `verification.md`.
