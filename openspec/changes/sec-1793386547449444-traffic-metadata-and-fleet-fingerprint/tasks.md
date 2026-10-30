# SEC-1793386547449444: Close traffic-metadata retention and fleet-fingerprint audit findings

## Objective

A default node writes no per-connection device, address or destination record; a production P1 host serves an operator-owned decoy with one identity for every probe outcome; REALITY validation reports key-share and DNS consistency; emitted clients probe latency every 30 minutes.

## Ownership

Primary: this repository. Ansible roles `xray`, `hysteria`, `nginx-xhttp`, `reality-self-steal`; `ansible/group_vars/all.yml`; `scripts/reality_target_validation.py`, `scripts/client_payload.py`; `secrets/prod.secrets.example.yaml`; matching tests, snapshot goldens and documentation. No client-repository contract change.

## Execution

- [x] SEC-1793386902478660 Retain no per-connection transport metadata by default in Xray and Hysteria #bug !high @item:SEC-1793386547449444
- [x] SEC-1793386903380604 Make the P1 decoy operator-owned and probe-consistent and retire the public example XHTTP path #bug !high @item:SEC-1793386547449444
- [x] SEC-1793386904380765 Validate REALITY identity consistency and slow the client latency probe then run the gates #bug !high @item:SEC-1793386547449444

## Verification

Local: `python3 -m pytest` on the touched test files, `make snapshot-check`, `make validate-secrets`, then `make check -j 4` once because the change spans Ansible, scripts and secrets handling. Remote CI: the pull request's full run at the exact head. Dry-run, staging, live and client gates are not authorized by this change; no host is touched. Artifact: refreshed snapshot goldens reviewed in the diff.
