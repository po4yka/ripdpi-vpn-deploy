# EPC-1795327697650892: Operate the VPN service without the operator workstation

## Objective

Coordinate W1 to W7 so a Claude cloud session with no secrets, the private ops repository CI and one egress VPS can deploy the whole service and change any operational setting while the operator MacBook is off.

## Ownership

The planner owns the epic and its dependency edges. Each child task owns its own paths. Shared files (`Makefile`, `mise.toml`, `docs/reference/testing.md`) are serialized in the order W2, W3, W4, W5, W6, W7.

## Execution

- [ ] EPC-1795327908893473 Track child tasks W1 to W7 and keep their blocked_by edges #epic !high @item:EPC-1795327697650892
- [ ] EPC-1795327923520670 Run the workstation-off acceptance drill after W7 and link its receipt #epic !high @item:EPC-1795327697650892

## Verification

Local: `./taskctl validate` and `./taskctl openspec cli validate --strict`. The epic closes after W1 to W7 are done and the workstation-off drill receipt (`REQ-WFO-ACCEPT`) is linked.
