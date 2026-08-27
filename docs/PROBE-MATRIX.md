# Topology-aware multi-protocol probe matrix

`vpnd probe-matrix` runs all configured protocol × target cells concurrently on a fixed schedule. It records authenticated data-plane verdicts without writing endpoint addresses or credentials to the report, then emits conservative observations for protocol-specific filtering, destination-class-wide collateral, and topology-specific dual-role targeting candidates.

This is a RESEARCH measurement workflow. Run it only from an authorized filtered path against owned targets, keep the default five-minute interval unless a reviewed experiment requires otherwise, and corroborate any observation independently before treating it as a filtering mechanism.

## Measurement dimensions

Protocols are `mtproto`, `xhttp-vless`, `xhttp-trojan`, `tcp-trojan`, and `tls-non-443`. The first four complete an authenticated or cryptographically established data path; the TLS cell completes hostname-verified TLS negotiation.

Destination classes remain technical signatures:

| Class | Meaning |
|---|---|
| `allowlist-pattern` | Destination class with historically distinct allowlist treatment. |
| `neutral-pattern` | Matched baseline class without known special treatment. |
| `non-allowlist-pattern` | Destination class without the allowlist response pattern. |

Each `comparison_set` contains exactly two targets in the same destination class: `single-ip-dual-role` and `split-hop-ingress`. Both targets must use identical Xray/mtg versions, ports, TLS posture, and transport parameters. Only credentials, endpoint addresses, and egress topology may differ.

## Operator artifacts

Copy `vpnd/config/probe-matrix.example.yaml` outside the repository. Its `profile_file` entries point to per-target JSON files generated with mode `0600`:

```bash
make decrypt ENV=staging
make emit-probe-matrix-profile \
  ENV=staging PROVIDER=upcloud \
  TARGET_ID=generic-dual \
  PROFILE_VARS=/absolute/path/to/target-vars.yml \
  PROFILE_OUTPUT="$HOME/.config/vpn-provision/probe-matrix/generic-dual.json"
```

The matrix configuration is schema version 2. The target profile is schema version 1. Their formal schemas are `contract/probe-matrix-config.schema.json` and `contract/probe-matrix-target.schema.json`.

The local runner requires `curl`, `openssl`, the same pinned Xray release declared by the target profile, Python with PyYAML, and the MTProto helper:

```bash
make probe-matrix-tools
export PROBE_MATRIX_MTPROTO_BIN="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}/vpn-provision-$(id -u)}/probe-matrix/bin/probe-matrix-mtproto"
```

Secrets are read only from the profile file. They are never passed through process arguments, environment variables, `--explain`, stderr, or report JSON.

## Running a sweep

```bash
vpnd probe-matrix --duration 4h --config /absolute/path/probe-matrix.yaml
vpnd probe-matrix --duration 30m --poll-interval-seconds 60 --config /absolute/path/probe-matrix.yaml
vpnd --explain probe-matrix --duration 4h --config /absolute/path/probe-matrix.yaml
```

Each tick first runs one direct HTTPS control through `make probe-matrix-control`. All cells then run concurrently through `make probe-matrix-cell`. Network failure is `blocked` only when the direct control is healthy; otherwise it is `unknown`. Runtime, version, profile, TLS-validation, authentication, malformed-output, and cleanup failures are `error`.

Ticks are scheduled from the original monotonic start time. A slow sweep does not shift every later tick; `sweep_duration_ms` and `overrun_ms` record when a sweep exceeds its interval. A duration or interval of zero is rejected. Both control and cell invocations have the configured control timeout; cancellation kills their captured process groups, including descendants.

## Report schema version 3

Reports default to `vpnd/state/probe-matrix-<unix-ms>.json`, an ignored operator-state directory. The formal schema is `contract/probe-matrix-report.schema.json`.

Each tick flushes a mode-0600 sibling journal and atomically replaces the mode-0600 JSON report. Append `.jsonl` to the complete report filename: `report.json` uses `report.json.jsonl`, while `report.txt` uses `report.txt.jsonl`. This preserves separate journals for concurrent reports with the same stem, including non-UTF-8 filenames. The JSONL stream contains initial, per-tick, and terminal records with `schema_version`, `timestamp_unix_ms`, `completed`, `interrupted`, `control` (object or null), and `cells`. Tick records contain only that tick's observations; status records have no cells. Keep the report and its journal together.

Each output also has an empty, mode-0600 `.lock` companion (`report.json.lock`). A nonblocking OS lock rejects another session using the same output before it changes either evidence file or starts probes. The lock file persists; the kernel releases its lock on normal exit or a crash, so the next run can reuse it. Do not delete or replace a lock file while a session may be active. Symlinked, foreign-owned, nonregular, nonempty, or incorrectly permissioned locks are rejected without removal. An output extension, when present, must be ASCII; `.jsonl` and `.lock` are reserved regardless of case. This prevents companion collisions on filesystems that fold case or Unicode-equivalent suffixes. Basenames remain unrestricted, including non-UTF-8 bytes where the filesystem supports them.

`completed: false, interrupted: false` identifies a running checkpoint; an abrupt crash leaves this explicitly unfinished evidence. A normal finish sets `completed: true`, which describes execution completion, not a healthy network verdict. SIGINT/SIGTERM stop child processes, preserve completed cells, mark unfinished cells `unknown`, and flush `interrupted: true, completed: false` before exiting with code 130/143. Indeterminate partial ticks never become positive filtering observations. The report schema is 3; input configuration remains schema 2 and target profiles remain schema 1.


Every cell contains `tick`, `timestamp_unix_ms`, `protocol`, `target_id`, `comparison_set`, `destination_class`, `topology`, `verdict`, optional `rtt_ms`, and optional categorical `error_kind`. It never contains the target endpoint. Windows describe separate episodes per protocol and target. Only `blocked` or `throttled` opens an episode; `last_impaired_unix_ms` advances only on another such sample. An adjacent `ok` supplies `recovery_unix_ms`. An `unknown` or `error` ends the episode at its last observed impairment, without claiming recovery across the evidence gap. Healthy or indeterminate-only series have no windows. Controls and analyzer observations are top-level arrays.

The analyzer emits:

- `protocol-specific` when one protocol is blocked or throttled across both topologies and at least two destination classes while another protocol remains healthy on each affected target.
- `destination-class-wide-collateral` when every selected protocol is blocked across both topologies in one destination class while another complete class remains usable.
- `dual-role-targeting-candidate` when every selected protocol is blocked on the single-IP target while matched split-hop targets remain usable across at least two destination classes.
- `indeterminate` when required evidence contains `unknown` or `error`; indeterminate ticks never emit a positive filtering observation.

These labels are evidence summaries, not causal proof.

## Provisioning the research stand

Enable `probe-matrix-target` only on explicit lab hosts with `allow_research_roles: [probe-matrix-target]`. Configure five distinct public TCP ports in `probe_matrix_target`, declare the same ports in Terraform `public_listeners`, and populate `probe_matrix_target_secrets` in the host's SOPS file. The role installs an auxiliary Xray target, pinned mtg, and a TLS-only nginx listener without modifying the family transport services.

For a split-hop target, Node A additionally enables `split-hop-ingress` and Node B enables `split-hop-egress`; both roles must be explicitly allowlisted. Node B remains the WireGuard initiator. Node A marks only new original-direction sockets from the dedicated probe Xray/mtg users, so replies on client-initiated flows keep the ingress route.

Run `make validate` before deploying these Ansible or Terraform changes. After deployment, prove all five cells from an unfiltered control vantage before collecting filtered-path evidence.
