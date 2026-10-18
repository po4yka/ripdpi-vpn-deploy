# SEC-1792307003680932: Repair network protocol correctness audit defects

## Objective

Close the confirmed network audit defects with source regressions and an
integrated, reviewed PR. Keep deployment and conditional risks separate.

## Ownership

- Network worker owns NAT outputs/tests/docs in all four provider roots and
  the inert cascade root, terraform/CLAUDE.md and terraform/README.md,
  scripts/render-inventory.sh NAT metadata, firewall and split-hop-egress NAT
  templates/admission/notes, ansible/roles/nginx-xhttp HSTS template/CLAUDE.md, matching tests,
  docs/PROVIDER-NOTES.md and docs/PUBLIC-SITE.md if present.
- Certificate worker owns scripts/check-certs.sh and certificate helper/callers,
  tests/unit/test_check_certs_key_match.py and focused new certificate tests,
  docs/CERTIFICATES.md if present. Coordinate any Makefile/controller caller
  change with the primary before editing.
- Client worker owns scripts/check-singbox-killswitch.py,
  scripts/transport_destination_policy.py, scripts/cascade-classifier-proxy.py,
  scripts/transport_egress_normalizer.py, matching test files and
  docs/CLIENT-NOTES.md. No client_payload.py changes.
- Client worker also owns scripts/workspace-status.py,
  tests/unit/test_workspace_status.py and one separate scripts/CLAUDE.md
  paragraph for the confirmed metadata pipe deadlock. The primary serializes
  that shared note and task artifacts; no other session implements this fix.
- Primary owns the AWG source correction helper/assets, production role
  integration and build identity after the network worker stopped. Certificate
  worker owns focused source-admission tests and independent review. Client worker
  owns native build consumers and the deterministic checksum regression. They
  agree the shared helper interface before edits; no runtime-cache core edits.
- Primary owns baseline resolver and DNS-Morph retirement integration,
  ansible/playbooks/site.yml, shared scripts/CLAUDE.md and tests/CLAUDE.md,
  snapshots, docs/TESTING.md, docs/NETWORK-PROTOCOL-AUDIT.md, task artifacts,
  integration, commits, review, CI and PR lifecycle.
- Other sessions retain Hysteria redirect, SSH, state backup, DHCPv6, and token
  lifecycle ownership. No agent edits another session's worktree. Shared notes
  are appended in separate paragraphs; board changes use taskctl only.

## Execution

- [x] SEC-1792307138300077 Repair UpCloud return policy and nginx HSTS with regressions #bug !high @item:SEC-1792307003680932
- [x] SEC-1792307139966331 Verify public certificate trust and enabled profile scope #bug !high @item:SEC-1792307003680932
- [x] SEC-1792307141621739 Preserve strict TUN capture DNS identity and socket lifecycles #bug !high @item:SEC-1792307003680932
- [x] SEC-1792307142612713 Restore managed DNS resolver after bridge retirement #bug !high @item:SEC-1792307003680932
- [ ] SEC-1792307143659844 Integrate coordinated fixes run complete gates review and merge #bug !high @item:SEC-1792307003680932

## Verification

Run focused behavior tests, provider tests, reviewed snapshots, complete make
check, security review, structured review and protected PR checks. Retain source
merge and exact integration CI evidence separately from local and device proof.
No deployment, live credentials, provider mutation or real notification occurs.
- [x] SEC-1792317891777907 Bound checkout metadata input without a duplex pipe deadlock #bug !high @item:SEC-1792307003680932
- [ ] SEC-1792321613767971 Normalize computed zero UDP checksums in pinned AWG builds #bug !high @item:SEC-1792307003680932
