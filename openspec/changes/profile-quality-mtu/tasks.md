# OPS-1792759217301702: Select profiles by transfer quality and diagnose MTU

## Objective

Deliver opt-in measured quality selection through the existing recipient
selector and scoped packet-size diagnosis, with bounded work and positive
native acceptance.

## Ownership

- Primary owns `docs/tasks/issues/profile-quality-mtu.md`, this OpenSpec change,
  generated board, `docs/reference/ripdpi-bundle.md`, related documentation and
  shared `CLAUDE.md` updates, combined validation and GitHub integration.
- Server implementation agent owns `scripts/payload_failover_policy.py`,
  necessary `scripts/client_payload.py` call sites, `scripts/payload_probe_content.py`,
  `scripts/serve-payload-probe.py`, `contract/ripdpi-bundle.schema.json`,
  `contract/ripdpi-bundle.payload-failover.json` and matching unit/emitter/socket
  tests. Shared contract files have one writer in this repository.
- Paired recipient implementation agent owns client runtime policy/parser,
  durable budget, candidate measurements and adapters, existing selector,
  observable measurement store, mirrored contracts and native acceptance.
- Primary owns client MTU diagnosis, profile/diagnostic presentation, all locale
  sets and their tests in a separate worktree. Integrate before combined gates.
- No agent may overwrite another lane or mutate live infrastructure. Heavy
  builds use the shared build gate. Task lifecycle is serialized by primary
  in this repository and the recipient task owner in the paired repository.

## Execution

- [ ] OPS-1792759876681957 Implement and verify version 2 quality policy admission and exact bundle emission #feature !high @item:OPS-1792759217301702
- [ ] OPS-1792759877415719 Serve bounded concurrent HEAD and verified payload transfers with real socket regressions #feature !high @item:OPS-1792759217301702
- [ ] OPS-1792759878148038 Integrate durable quality budgets and stable selection in the paired native recipient #feature !high @item:OPS-1792759217301702
- [ ] OPS-1792759878904355 Expose measured quality and scoped MTU diagnosis with real packet evidence #feature !high @item:OPS-1792759217301702
- [ ] OPS-1792759879627556 Complete positive acceptance independent review local gates and protected PR main integration #feature !high @item:OPS-1792759217301702

## Verification

Run focused producer, contract, emitter and actual HTTP/TLS/SOCKS regressions,
then strict OpenSpec, task/federation validation, docs checks and `make check`.
The paired client runs parser/model/service/selector/UI tests, locale and
architecture checks, real QUIC packet-size tests and owned native runtime
quality acceptance. Require independent review and protected exact-source
PR/main CI for both repositories. Live deployment and physical-device results
are outside this source task and are never inferred from isolated tests.
