# OPS-1795351496232576: Carry the ops repository capability and prove its inputs with a dry-run

## Objective

W1's private ops repository capability reaches the main specs with recorded evidence, and a check-mode dry-run through the ops inventory shows the same host selection and inputs as the kit.

## Ownership

This change directory and its task file only; no code paths.

## Execution

- [ ] OPS-1795351556503213 Record the merged W1 implementation, ops repository and import evidence against the carried spec #feature !high @item:OPS-1795351496232576
- [ ] OPS-1795351595564040 Run a check-mode dry-run through the ops inventory and compare host selection with the kit (authorized live step) #feature !high @item:OPS-1795351496232576

## Verification

Evidence from pull requests 683 (implementation, CI) and 686 (live ops repository, merge gate, import). Dry-run (authorized): `make dry-run ENV=p2-vultr ANSIBLE_LIMIT=node-c` with the ops `fleet.mk`, compared with the kit run. Local: `./taskctl validate`, `./taskctl openspec cli validate --strict`.
