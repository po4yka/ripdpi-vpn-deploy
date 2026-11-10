## Context

`scripts/bootstrap_readiness.py` is the only production caller that uses `StrictHostKeyChecking=accept-new`; deployment, inspection and liveness already use a pinned key with strict checking. The disposable CI lane on UpCloud pins the first contact: `scripts/ci-ssh-seed.py` builds a private image that holds a host key pair, `terraform/providers/upcloud/ci-ssh-seed.tf` imports it as encrypted storage and attaches it, and `terraform/shared/bootstrap-ssh-seed.py` installs the key at first boot after it checks the digest. The `ci_ssh_seed` variable is valid only for `ci-staging-*` environments. See proposal.md for the motivation.

## Goals / Non-Goals

- Goal: no production bootstrap path trusts an unknown host key without an explicit acknowledgement.
- Goal: reuse the proven seed mechanism instead of a second trust mechanism.
- Non-goal: SSH host certificates or a host key authority.
- Non-goal: a change to how deployment, inspection or liveness pin keys after bootstrap.
- Non-goal: rotation of host keys on existing nodes.

## Decisions

- Use the seed disk as the trust source. Rationale: it is implemented, tested, and it keeps private key material out of `user_data`. Rejected: host keys in cloud-init `ssh_keys`, because `user_data` stays readable through the metadata service and the hard rules forbid secrets there.
- Rejected: read the key fingerprint from the provider console after boot. No evidence in this repository shows that all four providers offer an authenticated console text interface, and a design must not depend on an unproven provider feature.
- Rejected: enroll the node in the tailnet first and connect over it. The enrollment key would have to travel in `user_data`.
- Roll out per provider on staging evidence. UpCloud first, because the mechanism runs there in CI. Each other provider gets the path only when a disposable run proves attach-at-creation and exact cleanup.
- Where no seed path exists, refuse by default and offer one acknowledgement flag per run. Rationale: the residual risk stays visible and is recorded; a silent fallback to `accept-new` would hide it.
- Rename the seed input and the builder script away from the `ci` prefix when they stop being CI-only, and update every consumer in the same change.

## Contracts and ownership

- Terraform: provider roots own the seed storage resource, its labels and its place in the destroy contract. The seed variable keeps its four fields (image path, image digest, filesystem UUID, public key digest).
- cloud-init: `terraform/shared/cloud-init.yaml.tftpl` passes only the filesystem UUID and the public key digest. `bootstrap-ssh-seed.py` keeps its read-only mount and digest check.
- Scripts: `bootstrap_readiness.py` owns the first-contact options; the seed builder owns the private image and the known_hosts pin; `destroy.sh` and the staging cleanup guards own exact removal.
- Local operator kit: holds the seed image and pin from creation until the node is enrolled, then only the pin.

## Risks / Trade-offs

- The operator machine generates the host private key, so that machine can impersonate the node. Mitigation: the image is private, single-use and deleted after first boot proof; the operator machine already holds the deployment secrets.
- One more billed storage resource per node. Mitigation: the smallest storage size, and detach and delete after the key is installed where the provider allows it.
- A provider may not support attach-at-creation. Mitigation: the per-provider evidence step and the explicit refusal.
- The acknowledgement flag can become a habit. Mitigation: it is per run, it is recorded in the enrollment record, and acceptance checks report it.

## Migration Plan

Existing nodes keep their keys and pins; this change applies to nodes created after it. Forward: enable the seed path on UpCloud, switch readiness to strict checking for seeded nodes, then add the refusal for unseeded providers together with the acknowledgement flag. Rollback: remove the seed input from a node's tfvars and pass the acknowledgement; no host state changes. Rollout gate: a disposable staging run on the provider before its root accepts the seed input.
