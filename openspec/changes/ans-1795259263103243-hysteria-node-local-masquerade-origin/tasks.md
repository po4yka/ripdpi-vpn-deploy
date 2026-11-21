# ANS-1795259263103243: Serve the Hysteria masquerade site from a node-local origin

## Objective

A `vpn-p2-udp` node without a web frontend serves its Hysteria masquerade site from content on the node itself, over HTTP/3 and the TCP masquerade listeners, so a probe of the node address gets a site that the node actually hosts.

## Ownership

`ansible/roles/hysteria/` (masquerade configuration, origin admission, defaults and role note), the site bundle consumer of `ANS-1795162466557355`, `ansible/group_vars/vpn-p2-udp.yml`, snapshot goldens of the Hysteria configuration, and their tests under `tests/unit/`. One writer at a time for the Hysteria configuration template.

## Execution

- [ ] ANS-1795259522975988 Admit a file masquerade origin and refuse a missing, empty or foreign-writable published tree #feature @item:ANS-1795259263103243
- [x] ANS-1795259540409372 Select the node-local origin from the site bundle on vpn-p2-udp and keep the proxy origin without one #feature @item:ANS-1795259263103243
- [x] ANS-1795259558601403 Update the Hysteria role note, snapshots and unit tests #feature @item:ANS-1795259263103243
- [ ] ANS-1795259578931298 Run staging acceptance of HTTP/3, HTTPS and HTTP answers from the node-local site #feature @item:ANS-1795259263103243

## Verification

Local: the Hysteria configuration and masquerade unit tests, `make snapshot-check`, `make molecule-test ROLE=hysteria`. Remote CI: the PR plan for the Hysteria role. Dry-run: `make dry-run` on a `vpn-p2-udp` node shows the `file` masquerade and the published site tree. Staging: a disposable `vpn-p2-udp` node answers HTTP/3, HTTPS and HTTP from the node-local site. Live: the next deploy of a production `vpn-p2-udp` node. Client: not applicable, no client contract changes. Artifact: not applicable.
