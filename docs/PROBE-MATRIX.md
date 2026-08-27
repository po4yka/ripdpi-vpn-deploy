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

Ticks are scheduled from the original monotonic start time. A slow sweep does not shift every later tick; `sweep_duration_ms` and `overrun_ms` record when a sweep exceeds its interval.

## Report schema version 2

Reports default to `vpnd/state/probe-matrix-<unix-ms>.json`, an ignored operator-state directory. The formal schema is `contract/probe-matrix-report.schema.json`.

Every cell contains `tick`, `timestamp_unix_ms`, `protocol`, `target_id`, `comparison_set`, `destination_class`, `topology`, `verdict`, optional `rtt_ms`, and optional categorical `error_kind`. It never contains the target endpoint. Windows are keyed by protocol and target. Controls and analyzer observations are top-level arrays.

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
