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
| REQ-EDF-ENFORCE | SEC-1794160777177995 | Pending: staging denial on P0, P1 and Hysteria2 | Not run |
| REQ-EDF-ALLOW | SEC-1794158301568776 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` | Local pass |
| REQ-EDF-INPUT | SEC-1794158806186281 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py`; generation-level rollback pending Molecule in CI | Local pass for parser, digest and source checks |
| REQ-EDF-CONTROL-PATHS | SEC-1794159684079419 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` | Local pass |
| REQ-EDF-PRIVACY | SEC-1794158301568776 | `python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py` captures process output | Local pass |
| REQ-EDF-BOUNDS | SEC-1794157748624712 | Local CPython measurement: 137 MB peak at the limits, 92 MB at 363,724 names and 50,000 addresses | Partial; the smallest node class is not measured |
| REQ-EDF-COVERAGE | SEC-1794160231676642 | `docs/reference/transport-egress.md` and `docs/reference/client-notes.md`; `make check` | Local pass |
