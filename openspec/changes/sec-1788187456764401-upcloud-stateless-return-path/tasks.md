# SEC-1788187456764401: Preserve return traffic through the UpCloud stateless firewall

## Objective

Deliver the phased activation and complete return-path contract described by
the linked task and delta specification.

## Ownership

- Own the UpCloud Terraform root, its focused tests and provider/operator docs.
- Do not edit, merge or apply draft PR110.
- Keep credentials, state, plans, UUIDs and live evidence outside Git.

## Execution

- [x] SEC-1788187699228713 Implement phased UpCloud firewall activation and dual-stack return rules #bug !crit @item:SEC-1788187456764401
- [x] SEC-1788187712724429 Prove return-path ordering, validation and unchanged exposure contracts #feature !high @item:SEC-1788187456764401
- [x] SEC-1788187713417276 Document phased activation, rollback and residual exposure boundary #feature !high @item:SEC-1788187456764401
- [ ] SEC-1788187714043182 Run isolated staging activation, acceptance and exact-resource cleanup #feature !crit @item:SEC-1788187456764401
