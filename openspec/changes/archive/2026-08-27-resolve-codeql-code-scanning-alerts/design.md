## Context

CodeQL analyzed `main` at `cfb52893594d4f7c9c9f423787f872f4935206ad`
with the repository's existing `security-extended,security-and-quality` query
set and reported alerts 320 through 327. Five findings are behavior-neutral
redundancies. The two empty-handler findings require explicit intent or safe
diagnostics. The high-severity file-mode finding intersects the monitoring
role's runtime contract: the Xray exporter writes as `xray`, while
node_exporter must read the completed Prometheus textfile.

## Goals / Non-Goals

- Goal: eliminate the eight identified findings at their causes while keeping
  CodeQL configuration and alert state untouched.
- Goal: replace world-readable Xray metrics with an explicit shared-group read
  contract that survives both fresh install and convergence over an existing
  `0644` file.
- Goal: preserve current fail-closed taskctl, monitoring, and liveness behavior
  with focused regression coverage.
- Non-goal: dismiss existing alerts, add CodeQL suppressions, change query
  packs, broaden workflow permissions, or refactor surrounding Python.
- Non-goal: deploy or converge a live node during this remediation; local,
  hosted-CI, and live evidence remain distinct.

## Decisions

- Change `vpn_xray.prom` from `0644` to `0640` in both the atomic writer and
  Ansible's existing-file convergence task. `0600` was rejected because the
  exporter and node_exporter intentionally run as different unprivileged
  accounts.
- Add the distro node_exporter account (default `prometheus`) to the existing
  `node_exporter_textfile` group and restart the service only when membership
  changes. Reusing the role-owned setgid/sticky group preserves the existing
  multi-producer boundary; the sticky directory prevents the collector from
  replacing another producer's file.
- Keep the Xray one-shot as file owner and group member. Atomic rename remains
  on the same filesystem, so readers see either the complete prior metric or
  the complete new metric.
- On a collection error, retain the best-effort failure metric. If that write
  also raises `OSError`, emit only the exception class in a separate stderr
  diagnostic, then emit the existing redacted collection failure and return
  one. Raw output, file content, and credential-bearing data remain excluded.
- Keep local-port connection refusal as a bounded retry. Add an explanatory
  handler comment rather than logging every expected refusal or changing loop
  control, either of which would add noise or alter multi-port readiness.
- Remove `sys`, `os`, and `shutil` imports where unused. Replace the mixed
  `unittest` import forms with one `from unittest import TestCase, main, mock`
  form and update the two module-qualified uses. Call
  `prepare_dropped_execution` for its side effects without retaining the path
  that is deterministically recomputed after the issue document is written.

## Contracts and ownership

- `ansible/roles/monitoring/` owns package accounts, the shared textfile group,
  service restarts, Xray exporter installation, and converged file mode.
- `ansible/roles/monitoring/files/xray-stats-exporter.py` owns atomic content
  publication and redacted runtime diagnostics.
- `scripts/vpn-protocol-liveness.py` owns the bounded listener-readiness loop;
  `scripts/monitor-protocol-liveness.py` only loses an unused import.
- `scripts/tasks/taskctl.py` and `scripts/tests/test_taskctl.py` own the task
  lifecycle compatibility change. `tests/unit/test_vultr_control_plane.py`
  only loses an unused import.
- No Terraform root, cloud-init input, SOPS secret, secrets schema, public vpnd
  CLI, network listener, or cross-layer data contract changes.
- `.github/workflows/codeql.yml` stays unchanged and remains the hosted source
  of truth for final alert closure.

## Risks / Trade-offs

- A service account could keep its old supplementary-group set until restart →
  notify the existing node_exporter restart handler on membership change and
  verify effective runtime readability in Molecule.
- A mode-only unit test could pass while node_exporter cannot scrape the file →
  assert account membership and query the running collector output in Molecule.
- Logging the fallback `OSError` could disclose a path through its message →
  log only `type(exc).__name__`, matching the existing redaction style.
- A comment-only empty-handler fix could mask changed readiness semantics → keep
  the code path behavior-identical and run the sentinel's slow-start,
  timeout, process-exit, and cleanup regression tests.
- Local tools cannot prove GitHub alert closure → keep remote CodeQL evidence on
  the exact final SHA required and report it separately from local validation.

## Migration Plan

1. Converge the monitoring role: install the package account, add it to the
   shared textfile group, repair any existing `vpn_xray.prom` to `0640`, and
   restart node_exporter if its group membership changed.
2. The next Xray exporter run atomically publishes a new `0640` file. Existing
   dashboards retain the same metric names and values.
3. Run focused Python tests, monitoring Molecule, task-contract validation,
   `make ci-fast`, and `make validate`. Do not treat a Docker/toolchain-only
   blocker as passed evidence.
4. After an authorized push or PR, require the hosted `codeql (python)` job on
   the exact implementation SHA and re-query alerts 320 through 327.
5. Rollback, if required, restores the previous source and role mode together;
   this reopens world readability and is therefore an emergency compatibility
   rollback only, not an acceptable completed state. Disabling Xray diagnostics
   remains the safe operational rollback because the role removes the metric
   and exporter artifacts completely.
