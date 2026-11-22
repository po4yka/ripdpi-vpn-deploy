# SCR-1795352512092131: Trust an explicit staging TLS anchor in the disposable liveness executor

## Objective

`make provision-disposable-liveness-runtime STAGING_TRUST_ANCHOR=<cert>` validates one self-signed staging certificate and installs it into the disposable executor's trust store, so the four-profile proof verifies TLS on a self-signed disposable staging node.

## Ownership

`scripts/provision-disposable-liveness-runtime.py`, the `provision-disposable-liveness-runtime` Make target and its command-variable list in `Makefile`, `tests/unit/test_provision_disposable_liveness_runtime.py`, `tests/unit/test_disposable_liveness_make.py`, `docs/reference/protocol-liveness.md`. One writer.

## Execution

- [x] SCR-1795352837575574 Add the optional staging trust anchor to the executor provisioning script and Make target #feature !high @item:SCR-1795352512092131
- [x] SCR-1795352930293878 Document the staging trust anchor in the protocol liveness reference #feature !high @item:SCR-1795352512092131
- [x] SCR-1795371731256603 Make the liveness Xray XHTTP profile verify against the system CA store #feature !high @item:SCR-1795352512092131
- [ ] SCR-1795353017817845 Prove four-profile ok on a disposable staging node with the anchor #feature !high @item:SCR-1795352512092131

## Verification

- Local: `python3 -m pytest tests/unit/test_liveness_profiles.py tests/unit/test_provision_disposable_liveness_runtime.py tests/unit/test_disposable_liveness_make.py`, `make docs-check`.
- Remote CI: PR checks.
- Dry-run: not applicable (no deployed runtime change).
- Staging: one disposable UpCloud node, executor provisioned with the anchor, fresh `ok` for `p0-reality`, `p1-xhttp`, `p2-hysteria2` and `p2-amneziawg`.
- Live, client, artifact: not applicable.
