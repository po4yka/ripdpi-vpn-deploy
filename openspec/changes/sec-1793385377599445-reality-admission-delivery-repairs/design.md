## Context

The proposal lists six defects. All of them sit in repository-owned rendering, admission and emission code, so none needs a Terraform, provider or live-host change in this slice. Runtime effects reach existing nodes only through a separately authorized deploy.

## Goals / Non-Goals

- Goal: every rendered REALITY inbound has a bounded client time window.
- Goal: production Xray acquisition refuses a version that was never reviewed for production. Upstream release flags, which a tag string cannot encode, do not decide this.
- Goal: watchdog and smoke probes, share URIs and bundle topology describe what recipients actually use.
- Goal: new XHTTP paths are unguessable, and the published example path is never served.
- Non-goal: rotating existing operator XHTTP paths, credentials or Xray pins.
- Non-goal: changing the RIPDPI bundle schema, `new-client.sh --emit-uri` issuance templates, or the split-hop research topology.
- Non-goal: `minClientVer`, per-cohort REALITY identity, or PQE. Those are separate decisions.

## Decisions

### REALITY replay window
- `xray_reality_max_time_diff_ms` lives in the xray role defaults, set to 90000. The value is in milliseconds, Xray's unit.
- The shared template renders the value into every REALITY inbound.
- The role preflight asserts a positive integer.
- Rejected alternative: leaving it to Xray's default. Xray's default is zero, which disables the check.

### Production pin admission
- `xray_runtime_production_versions` lives in the xray-runtime defaults. `xray-runtime` is the single acquisition point for the xray role, the transport-egress gateways and research targets.
- The assert runs before any download or build. It reads `env` the way the Snell staging guard does: the host var `env`, then the `ENV` environment variable.
- `scripts/check-xray-version-pin.py` also fails when the allowlist omits the release tracker's repository pin.
- Rejected alternative: a tag-shape regex. Upstream Xray prereleases carry plain `vX.Y.Z` tags.
- Rejected alternative: a live GitHub lookup at deploy time. It is a network dependency, and a Latest release is not qualified.

### Probe fingerprint
- The watchdog and smoke templates read `xray_utls_fingerprint | default('chrome')`, the same input `client_payload.py` uses for REALITY and XHTTP recipients.
- The XHTTP watchdog client also gains `tlsSettings.fingerprint`.

### Share URI
- `client_payload.py --share-uri` materializes the sing-box format for the selected device. It requires exactly one REALITY outbound and prints one `vless://` URI built from that outbound:
  - `type=tcp`, `encryption=none`, `security=reality`;
  - `sni`, `fp`, `pbk`, `sid`, optional `flow`;
  - the outbound tag as the fragment.
- `emit-qr.sh --type uri` calls it and drops its enrollment branch.
- Rejected alternative: keep issuance and add Terraform resolution after enrollment. Rendering a QR code would still have a credential side effect, and the existing `--type singbox` mode is already read-only.

### Bundle topology
- The emitter no longer ORs `enable_split_hop_ingress` into `split_hop_egress`. The responder marks only the research probe runtime UIDs (`roles/split-hop-ingress`), so no emitted family outbound egresses through Node B.
- The schema field stays false until a family transport is routed through Node B.

### XHTTP path
- Bootstrap emits `openssl rand -hex 16`.
- `transport_semantics.xhttp_errors` refuses an absent path and the literal `/app-sync`. `xhttp_path_valid` keeps syntax-only admission.
- Consumers drop their silent `/app-sync` fallbacks, and fixtures, Molecule inputs and goldens use non-default paths.
- Rejected alternative: a minimum-length refusal for existing paths. It would force P1 re-issuance for every device at the next production deploy. The operator chose to keep existing explicit paths admissible.

## Contracts and ownership

- **Ansible:** `roles/xray/{defaults,tasks/enable.yml,templates/config.json.j2}`, `roles/xray-runtime/{defaults,tasks/main.yml}`, `roles/watchdog/templates/reality-probe.json.j2`, `playbooks/tasks/smoke-reality.yml`, `roles/nginx-xhttp/templates/site.conf.j2`, `roles/cdn-front/defaults/main.yml`, plus Molecule inputs that used `/app-sync`.
- **Scripts:** `client_payload.py`, `emit-qr.sh`, `bootstrap-secrets.sh`, `transport_semantics.py`, `liveness_profiles.py`, `device_lifecycle_probe.py`, `check-xray-version-pin.py`.
- **Contracts and docs:** `secrets/prod.secrets.example.yaml`, `tests/fixtures/secrets-sample.yml`, snapshot goldens, `docs/reference/ripdpi-bundle.md`, `docs/reference/xray-release-line.md`, `docs/reference/client-notes.md`, and the affected role notes.

## Risks / Trade-offs

- A device clock skewed beyond 90 s loses P0. Mitigation: the window is configurable per profile, and `client-notes.md` documents the symptom (the client sees the borrowed target's certificate).
- Adding a production Xray release becomes a reviewed allowlist edit. This is intended: it moves qualification into review.
- `emit-qr --type uri` no longer issues devices. Operators issue with `new-client.sh` first; the usage text and docs say so.
- An operator whose real secrets still say `/app-sync` gets a refusal at the next deploy. That path is published and must be rotated anyway; the refusal names the field.

## Migration Plan

- **Forward:** merge, then run an authorized `make deploy` per node. The replay window and probe fingerprints apply on converge.
- **Production pins:** a production pin outside the allowlist refuses before acquisition. Today the only production pin is `v26.3.27`, which is in the list.
- **Rollback:** revert the commit and redeploy. Rendered-config rollback through `rollback-config.yml` keeps working, because the previous configuration simply has no `maxTimeDiff`.
- **Gates:** local narrow checks, then `make check`, then PR CI. Dry-run, staging, live and client evidence are deferred to the authorized deploy.
