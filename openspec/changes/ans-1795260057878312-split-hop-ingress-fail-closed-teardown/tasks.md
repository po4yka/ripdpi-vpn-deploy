# ANS-1795260057878312: Make split-hop ingress flows fail fast after the tunnel stops

## Objective

When the split-hop WireGuard tunnel on Node A stops, forwarded device flows and local frontend connections that the policy routes to Node B fail at once with an error, instead of waiting for a timeout behind a silent drop. They never leave through the direct uplink.

## Ownership

`ansible/roles/split-hop-ingress/` (tunnel `PostUp`/`PostDown`, policy tables, policy loader unit, retirement tasks and role note), snapshot goldens of its templates, and their tests under `tests/unit/`. Coordinate with the open split-hop changes before editing `policy.nft.j2`; one writer at a time for that file.

## Execution

- [ ] ANS-1795260140617842 Keep the split-hop rule and an unreachable default route in the policy table while the tunnel is down #feature @item:ANS-1795260057878312
- [ ] ANS-1795260176389101 Reject new marked frontend UID connections in the output hook while the tunnel interface is absent #feature @item:ANS-1795260057878312
- [ ] ANS-1795260207966094 Remove the rule, the kept route and the reject rule on retirement, with snapshot and unit tests #feature @item:ANS-1795260057878312
- [ ] ANS-1795260239530010 Run staging acceptance on a disposable pair: immediate errors with the tunnel down, no direct-uplink packets, clean retirement #feature @item:ANS-1795260057878312

## Verification

Local: the split-hop ingress unit tests, `make snapshot-check`, `make molecule-test ROLE=split-hop-ingress`. Remote CI: the PR plan for the split-hop roles, including the native split-hop lane. Dry-run: `make dry-run` on a split-hop ingress node. Staging: a disposable Node A and Node B pair where stopping the tunnel makes a device flow and a local frontend connection fail within a second, with no packet on the direct uplink. Live: not applicable until a production split-hop pair exists. Client: not applicable. Artifact: not applicable.
