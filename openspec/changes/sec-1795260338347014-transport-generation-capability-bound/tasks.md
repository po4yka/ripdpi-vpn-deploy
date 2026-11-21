# SEC-1795260338347014: Bound the capabilities of the transport generation controller

## Objective

`ripdpi-transport-generation.service` runs with a capability bounding set that holds only the capabilities its operations need, and every operation of the controller still works under that set on a native Linux host.

## Ownership

`ansible/roles/transport-egress/templates/generation.service.j2`, the controller code under `ansible/roles/transport-egress/files/` only where an operation must change to fit the set, the native transport acceptance tests, snapshot goldens and the role note. One writer at a time for the unit template.

## Execution

- [ ] SEC-1795260399016884 List each controller operation and the capability it needs, with a failing native test as evidence for each #feature @item:SEC-1795260338347014
- [ ] SEC-1795260429892810 Set the CapabilityBoundingSet on the generation unit and record the reason for each capability in the role note #feature @item:SEC-1795260338347014
- [ ] SEC-1795260460933493 Run every controller operation under the bound in the native transport lanes and full-stack Molecule #feature @item:SEC-1795260338347014
- [ ] SEC-1795260492741288 Run staging acceptance with a reboot and a WARP namespace refresh under the bounded unit #feature @item:SEC-1795260338347014

## Verification

Local: `make snapshot-check` and the transport generation unit tests. Remote CI: the native transport lanes and the full-stack Molecule scenarios, which run the controller under systemd. Dry-run: `make dry-run` on a node with transport egress. Staging: a disposable node where the controller starts and stops frontends, drops to frontend UIDs, restores nft state after a reboot and refreshes the WARP namespace under the bounded set. Live: the next production deploy. Client: not applicable. Artifact: not applicable.
