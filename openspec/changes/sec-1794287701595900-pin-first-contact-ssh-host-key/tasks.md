# SEC-1794287701595900: Pin the SSH host key before first contact with a new node

## Objective

The first SSH connection to a new node uses strict host key checking against a key the operator held before the node existed, on every provider with a proven seed path. Other providers refuse first contact unless the operator acknowledges an unpinned connection for that run.

## Ownership

`terraform/providers/*/` (seed input, seed storage, destroy contract), `terraform/shared/cloud-init.yaml.tftpl` and `terraform/shared/bootstrap-ssh-seed.py`, `scripts/bootstrap_readiness.py`, `scripts/ci-ssh-seed.py`, `scripts/destroy.sh`, `scripts/staging-cleanup-guard.py` and `scripts/vultr-staging-cleanup-guard.py`, their tests under `tests/unit/` and `terraform/providers/*/tests/`, and the bootstrap pages under `docs/how-to/`. One writer at a time for `terraform/shared/` and `scripts/bootstrap_readiness.py`.

## Execution

- [ ] SEC-1794291848553555 Record per provider whether a private seed disk can be attached at creation, with a disposable staging run as evidence #feature !high @item:SEC-1794287701595900
- [ ] SEC-1794293005903024 Promote the seed-disk host key path to a supported production bootstrap input on UpCloud and on each provider the evidence step proved #feature !high @item:SEC-1794287701595900
- [ ] SEC-1794291241207370 Add the seed path to each further provider root that step one proved, with mock-provider and cleanup-guard tests #feature !high @item:SEC-1794287701595900
- [ ] SEC-1794294617246460 Make bootstrap readiness use the seeded known_hosts pin with strict checking and remove accept-new #feature !high @item:SEC-1794287701595900
- [ ] SEC-1794295778399562 Refuse first contact without a seed unless the operator passes a recorded unpinned-first-contact acknowledgement #feature !high @item:SEC-1794287701595900
- [ ] SEC-1794292461857569 Update bootstrap documentation and the first-contact tests #feature !high @item:SEC-1794287701595900
- [ ] SEC-1794294089752579 Run disposable staging acceptance of pinned first contact on every supported provider #feature !high @item:SEC-1794287701595900

## Verification

Local: `make tf-test`, `make tf-policy-verify`, the first-contact and seed unit tests, `make check`. Remote CI: the full PR plan including the disposable deploy lane. Dry-run: `make plan` for a seeded UpCloud node shows the seed storage and no private key bytes. Staging: one disposable node per supported provider with a pinned first contact, a refused mismatch and an exact cleanup. Live: the next production node created after the change. Client: not applicable, no client contract changes. Artifact: not applicable, no release artifact.
