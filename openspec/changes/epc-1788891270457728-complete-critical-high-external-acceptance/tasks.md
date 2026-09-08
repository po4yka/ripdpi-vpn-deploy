# EPC-1788891270457728: Complete Critical and High external acceptance gates

## Objective

Complete the remaining Critical and High acceptance from one exact protected
source through guarded staging, serial fleet convergence, current-client
traffic, alert recovery, offsite restore, and provider-confirmed cleanup. Keep
the task active with a precise blocker when an external capability is absent.

## Ownership

This task owns only its portfolio and OpenSpec artifacts plus private,
invocation-specific evidence outside the repository. During execution it owns
one serialized provider/network lane covering the selected Terraform state,
cleanup manifest, generated inventory, SSH contexts, staging identity, alert
authority, and restore destination. Existing runtime source is read-only unless
an observed acceptance failure requires a separate root-cause fix through
protected main. Other tasks must not mutate the owned provider, state, targets,
profiles, or evidence paths during an active invocation.

## Execution

- [ ] EPC-1788891640190305 Freeze exact protected source and complete the no-write external capability preflight #feature !crit @item:EPC-1788891270457728
- [ ] EPC-1788891640866927 Create and exercise one manifest-bound isolated staging node and verify provider cleanup #feature !crit @item:EPC-1788891270457728
- [ ] EPC-1788891641535013 Run fleet dry-run and serial convergence with SSH recovery security and source-drift proof #feature !crit @item:EPC-1788891270457728
- [ ] EPC-1788891642225067 Prove current-client four-transport traffic and fresh recurring AmneziaWG acceptance #feature !high @item:EPC-1788891270457728
- [ ] EPC-1788891642969936 Prove primary and dead-man alert recovery plus isolated offsite restore #feature !high @item:EPC-1788891270457728
- [ ] EPC-1788891643660976 Reconcile every predecessor obligation and complete exact-evidence closure #feature !crit @item:EPC-1788891270457728

## Verification

- **Local:** clean-source identity and deployable digest; credential-presence
  checks without values; strict SOPS, inventory, SSH-context, manifest, evidence
  ownership, and task/OpenSpec validation.
- **Remote CI:** all required protected-main checks pass for the exact source
  commit used by every external phase.
- **Dry-run:** canonical precheck and exact-target Ansible check mode complete
  serially for every configured Critical or High fleet target.
- **Staging:** one guarded isolated node proves SSH migration and recovery,
  listener/firewall parity, required runtime behavior, rollback, and
  provider-confirmed server and dependent-storage absence within its approved
  cost and expiry.
- **Live:** serial convergence reports zero failed or unreachable tasks, then
  `verify`, `security-verify`, and `source-drift` pass for every target without
  losing emergency SSH or required VPN paths.
- **Client:** a current signed artifact proves authenticated REALITY, XHTTP,
  Hysteria2, and AmneziaWG traffic; a distinct invocation proves fresh recurring
  AmneziaWG correlation, recovery, and teardown.
- **Artifact and operations:** both alert authorities fire and recover, the
  expected target set is fresh, an offsite copy restores into an isolated
  destination without pruning, and the final matrix maps all thirteen
  predecessor tasks to scope-matching evidence.
