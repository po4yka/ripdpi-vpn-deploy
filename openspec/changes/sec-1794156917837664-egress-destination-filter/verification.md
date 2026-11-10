---
task_id: SEC-1794156917837664
change: sec-1794156917837664-egress-destination-filter
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EDF-DEFAULT-OFF | SEC-1794158806186281 | `make snapshot-check` with the toggle disabled; `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` | Local pass; Molecule pending in CI |
| REQ-EDF-ENFORCE | SEC-1794158301568776 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` over real sockets with a fixture gateway | Local pass |
| REQ-EDF-ENFORCE | SEC-1794160777177995 | Staging run below: a listed name, its subdomain and a listed address are denied on P0, P1 and Hysteria2, with a one-hour soak | Pass for the step; the deployment controller did not run, so this is not deployment acceptance |
| REQ-EDF-ALLOW | SEC-1794158301568776 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` | Local pass |
| REQ-EDF-INPUT | SEC-1794158806186281 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py`; Molecule `transport-egress` scenario passed in CI on PR 541; the staging rollback below restored the prior generation | Pass |
| REQ-EDF-CONTROL-PATHS | SEC-1794159684079419 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` | Local pass |
| REQ-EDF-PRIVACY | SEC-1794158301568776 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` captures process output | Local pass |
| REQ-EDF-BOUNDS | SEC-1794157748624712 | Staging run below: 66 MB resident and 94 MB peak in the normalizer, 138 MB peak for its service, on a 1 GB node with 363,724 names and 35,296 addresses | Pass; the process peak is below the 137 MB local peak at the limits, so the limits stay |
| REQ-EDF-COVERAGE | SEC-1794160231676642 | `docs/reference/transport-egress.md` and `docs/reference/client-notes.md`; `make check` | Local pass |

## Staging run 2026-11-09

This run proves the filter on a live node. It is not deployment acceptance, so `staging_evidence` stays empty.

Deviations from the canonical path:

- The owner approved a direct `ansible-playbook` run of `site.yml` with the `ssh-transaction` tag skipped, because the disposable executor has no AmneziaWG toolchain and `make deploy` requires a four-profile proof.
- AmneziaWG and geodata were off for this run. The UpCloud node has IPv4 and IPv6 on separate interfaces, and the staging secrets generator supplies placeholder geodata pins.
- The source was `origin/main` at `5d8a03ea` plus two unpublished commits: the staging toggle and the signed Tailnet key fix.

Node: one UpCloud `1xCPU-1GB` node, 847 MB usable memory, source revision `290834b7`.

Deny data: commit `5c992c35301e6f3e4c84181b1dfd51873ca35a21` of `hagezi/dns-blocklists`, licence GPL-3.0 accepted by the owner. `wildcard/tif.medium-onlydomains.txt` has SHA-256 `b9a0d93a046a4c5cc2e344f298c9f2c42a4008bfb01e4fcf28048407936e2295`. `ips/tif.txt` has SHA-256 `231dc970240aaf96ecba2dad6345d0278777f47bd68cdde13bd5a24954585a79`.

| Check | Result |
|---|---|
| Allowed HTTPS on P0, P1 and Hysteria2 | 200 and 204 returned on each protocol |
| Listed name, its subdomain and a second listed name | Denied on each protocol; the same names return 200 directly from the node, outside the filter |
| Listed address | Denied on each protocol; the direct request from the node timed out, so it proves no reachability |
| One-hour soak, 60 samples per protocol | Denied requests: 180 of 180. Allowed requests: P0 60 of 60, P1 57 of 60, Hysteria2 60 of 60 |
| Allowed latency, median | P0 0.76 s, P1 0.69 s, Hysteria2 0.39 s. P0 and P1 had outliers near 16 s; the cause is not known |
| Normalizer memory over one hour | 66,260 KB to 66,284 KB resident, 93,952 KB peak |
| Normalizer service memory | 138 MB peak; node available memory stayed between 250 MB and 283 MB |
| Rollback | A filter-off candidate with a forced acceptance failure was rolled back. `normalizer.json`, `generation.json`, `policy.json` and `direct.json` hashes matched the prior generation, and denial still worked |

After the rollback, one P0 request to the listed address timed out instead of an immediate refusal. It did not connect.
