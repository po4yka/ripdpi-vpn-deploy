# SEC-1792306869763633: Repair audited security and delivery contracts

## Objective

Close all thirteen confirmed audit findings through source fixes, regressions, documentation and protected merge.

## Ownership

- Secrets/backup: setup-yubikey-age.sh, backup-tf-state.sh, associated helpers/tests; AGE-RECOVERY.md, SECRETS.md, RUNBOOK-rotate.md.
- HTTP/alerts: the three audited authenticated clients; observability_control_plane alert and Telegram relay code/notes/tests.
- Subscription: issue_sub_token.py, client_payload.py, validate-bundle.py; subscription-host publication/runtime/notes/tests and subscription documentation.
- Primary: SSH baseline renderer/controller/verifier/tests, task artifacts, snapshots and integration. Shared scripts/CLAUDE.md and tests/CLAUDE.md are serialized primary-only lanes. Workers submit proposed paragraphs.
- Workers share this worktree, preserve others' edits, and do not commit, push, alter lifecycle or execute infrastructure operations.

## Execution

- [x] SEC-1792306995752496 Repair secrets recovery and backup publication #bug !high @item:SEC-1792306869763633
- [x] SEC-1792306996420715 Repair authenticated HTTP and alert contracts #bug !high @item:SEC-1792306869763633
- [x] SEC-1792306997096858 Repair subscription publication and consumer admission #bug !high @item:SEC-1792306869763633
- [x] SEC-1792306997783845 Qualify hybrid SSH key exchange policy #bug !high @item:SEC-1792306869763633
- [ ] SEC-1792306998523204 Complete source runtime review and protected merge gates #bug !high @item:SEC-1792306869763633

## Verification

Focused regressions, rendered snapshots, complete make check, structured security review, protected exact-source CI and observed main merge. No external deployment or private credentials are part of this task.
