# Testing — what's covered and what isn't

The repo's defense-in-depth philosophy applies to its own correctness: every
config, role, and script is checked at multiple layers before it can hit a
real VPS. This doc enumerates each layer and where coverage gaps exist
(with explicit reasons).

Bootstrap-wait regressions require GNU `timeout` on the local test PATH. They
execute the real remote command under an isolated SSH transport fixture; the
production target uses its existing coreutils `timeout`, and the controller
uses Python's standard library for local SSH deadlines.

## Coverage matrix

| Artifact | Static check | Render check | Functional test (molecule) | Notes |
|---|---|---|---|---|
| **Terraform provider roots** | `terraform fmt -check` + `terraform validate` + `terraform test` (CI) | n/a | n/a | CI matrix runs UpCloud, Hetzner, Vultr, and Scaleway. |
| **Terraform — provider-specific invariants** | `terraform fmt -check` + `terraform validate` + `terraform test` (CI) | n/a | n/a | Native tests cover server/output invariants, honeypot IP allocation, firewall toggles, SSH scoping, XHTTP port behavior, and port validation. |
| **Terraform — inert cascade exception root** | `terraform fmt -check` + `terraform validate` (required CI) | n/a | n/a | Separate local state, no provider resource, normal router has no branch, plan requires a fresh attestation, and apply is unconditionally disabled under implementation-only governance. |
| **cloud-init template** | `cloud-init schema --config-file` (CI) | rendered from the Terraform template with CI stub vars + focused marker contract | n/a | Regression executes the rendered first-boot command and proves a failed SSH reload cannot publish the completion marker. |
| **cloud-final restart acceptance** | `pytest tests/unit/test_cloud_init_restart_acceptance.py` | exact rendered bootstrap source and digest-pinned Debian 13 / Ubuntu 24.04 Dockerfiles | manual `scripts/cloud-init-restart-acceptance.py --source-root … --output … --profile …` | Runs clean and interrupted cases in an isolated Colima profile, requires strict marker/ownership/effective-sshd evidence, and deletes the profile on every exit. A nonzero guest result may retain only a private redacted failure sidecar. Container PID1 restart is not provider reboot or staging proof. |
| **Ansible playbooks** | `ansible-lint` + `ansible-playbook --syntax-check` (CI) | n/a | n/a | site.yml asserts VPN_SECRETS_FILE is set; CI passes the example schema as a stub. |
| **Ansible smoke lifecycle** | ansible-lint | actual source task graph with local executable boundaries | `pytest tests/unit/test_smoke_test_cleanup.py` (57 cases; not Molecule) | Owned cleanup, retained-claim retries, concurrent invocations, subscription-only gating and client liveness; eight real-curl dynamic-loopback cases reject inherited NO_PROXY bypass. Linux systemd and deployed transport acceptance remain separate. |
| **Ansible role: baseline** | ansible-lint | render check | **molecule** (debian13 + ubuntu24.04) | tests sshd hardening, sysctl, timesync, IPv4 forwarding gating. |
| **Ansible role: package_updates** | ansible-lint | render check | **molecule** | fleet-baseline unattended security updates; verifies no automatic reboot and `unattended-upgrade -d --dry-run`. |
| **Ansible role: intrusion_prevention** | ansible-lint | render check | **molecule** | opt-in Fail2Ban sshd jail; verifies nftables action config, ignoreip merge with `allowed_ssh_cidrs`, and service health. In `site.yml` it can run before firewall; firewall still owns the durable nftables table and ban sets. |
| **Ansible role: firewall** | ansible-lint | render check | **molecule** | tests nftables.conf parse + presence of expected ports. |
| **Ansible role: network-exposure-gate** | ansible-lint + strict contract validation | reviewed exposure manifest and controller artifact binding | **molecule** | verifies the signed-review gate, no-follow artifact handling, exact host identity, and fail-closed handoff without changing firewall policy. |
| **Ansible role: tailnet-management** | ansible-lint + controller contract tests | exact-source firewall render and signed-package pin checks | **molecule** (converge + idempotence + verify) | Synthetic Tailscale and nftables commands prove stdin/file-only enrollment, exact disabled DNS/routes/SSH/netfilter flags, cleanup and unchanged repeat. Real Tailnet policy, control-plane enrollment, SSH identity, emergency path and VPN traffic remain staging/live gates. |
| **Ansible role: xray** | ansible-lint | render check (JSON validity) | **molecule** (converge + idempotence + verify) | synthetic release binary; config, unit and rollback checks retained. The isolated x86_64 QEMU-backed scenario passed converge, a zero-change second converge, verify and destroy. |
| **PQ-REALITY adoption policy** | `scripts/check-xray-breaking-changes.py` (pre-commit + CI + `make ci-fast`) | every rendered VLESS+REALITY inbound must retain `settings.decryption: "none"` | n/a while phase is HOLD | Unit tests cover single/multi-cohort renders, every violating inbound, selector scope, and fail-closed guard metadata. |
| **Ansible role: nginx-xhttp** | ansible-lint | render check (`nginx -t`) | **molecule** (idempotence + verify) | self-signed cert generated in pre_tasks; verifies no Cloudflare-specific directives leaked into the filtered-path baseline. |
| **Ansible role: cdn-front** | ansible-lint | render check (`nginx -t`) | **molecule** | required CI exercises refresh-service sandbox and nginx integration; opt-in role remains outside the filtered-path baseline. |
| **Ansible role: hysteria** | ansible-lint | render check | **molecule** (template-only, stub binary) | verifies clients render + Salamander disabled by default. |
| **Ansible role: amneziawg** | ansible-lint | render check | **molecule** (default sequence: dependency, syntax, create, prepare, converge, idempotence, verify, destroy) | synthetic local Git/Make inputs and no-TUN tools exercise role-owned builds, receipts, config and systemd lifecycle. The isolated x86_64 QEMU-backed scenario passed converge, a zero-change second converge, verify and destroy. No upstream build or tunnel proof. |
| **Ansible role: real-vps-awg-nat** | ansible-lint + focused provisioning contracts | render/source-policy checks + immutable offline-build fixtures | **local three-host evidence lane (not Molecule)** | Meaningful convergence requires three separate root/systemd/network namespaces, a physical TUN-capable sentinel, a public echo host, and an AWG/NAT VPS. Unit tests cover fail-closed rendering, transaction recovery, archive safety, and idempotent immutable tool reuse; the recurring Mac-to-sentinel-to-VPS lane is the functional and idempotency proof. A single privileged container cannot validate these trust and routing boundaries. |
| **Ansible role: monitoring** | ansible-lint | render check | **molecule** | verifies node_exporter + journald + logrotate. |
| **Ansible role: observability_agent** | ansible-lint + focused privacy/adapter contracts | render check + snapshots | **molecule** (default + required `enabled`) | Default-off staged sender; enabled scenario proves mTLS remote-write, bounded WAL/resources, outage accounting, authenticated drain, and idempotence. Live fleet rollout remains a separate acceptance gate. |
| **Ansible role: observability_control_plane** | ansible-lint + receiver/generation contracts | render check + snapshots | **molecule** (default + required `enabled`) | Dedicated default-off mTLS receiver; enabled scenario proves strict SNI/method/body/CN policy, loopback-only Prometheus, immutable config generations, capacity refusal, rollback, and idempotence. |
| **Ansible role: watchdog** | ansible-lint + `bash -n` (verify play) | render check | **molecule** + idempotence | verifies probe script syntax + env file perms + topic rendering. |
| **Ansible role: backup** | ansible-lint | render check + focused contract tests | **molecule** | exercises local and rclone-backed snapshots, real isolated restores, live-file non-mutation, cleanup, timer enable/disable, and remote failure without local fallback or marker replacement. |
| **Ansible role: subscription-host** | ansible-lint | render check (`nginx -t`) | **molecule** + idempotence | verifies revoked-tokens map + rate-limit zone + payload dir perms. |
| **Ansible role: geodata** | ansible-lint | render check | **molecule** (default sequence: dependency, syntax, create, prepare, converge, verify, destroy) | real downloader and sandboxed refresh service use pinned local fixture sources; upstream availability and an active Xray daemon remain live checks. |
| **Ansible role: naive** | ansible-lint | render check (Caddyfile syntax NOT validated — Caddy not in CI matrix) | **molecule** (default sequence: dependency, syntax, create, prepare, converge, verify, destroy) | xcaddy from-source build skipped in CI to avoid Go-module-network flakiness; `molecule converge` runs it locally. |
| **Ansible role: honeypot** | ansible-lint | render check + focused retention/dual-stack contracts | **molecule** + idempotence | verifies service active, separate IPv4/IPv6 listeners, script installed, timer active, and threshold-triggered rotation recreates a writable bounded log. |
| **Ansible role: policy-ratelimit** | ansible-lint | render check | **molecule** + idempotence | verifies daemon script + systemd unit + active state. nftables `policy_offenders` set is exercised in the full-stack scenario. **Decision-core logic** (token coupling, RFC1918 exemption, ban thresholds, dead-contract gauge) is unit-tested against golden Xray v26.3.27 log fixtures in `tests/unit/test_policy_ratelimit.py` — including the assertion that external REALITY probes (error.log) are never bannable. See `ansible/roles/policy-ratelimit/README.md`. |
| **Ansible role: warp-outbound** | ansible-lint | render check | **molecule** (default sequence: dependency, syntax, create, prepare, converge, verify, destroy) | command fixtures exercise the actual health and signing-key gates; real registration, tunnel egress, and filtered-path reachability remain live checks. |
| **Ansible role: dns-morph-bridge** | ansible-lint | render check | **molecule** (converge + idempotence + verify) | binary install skipped when `binary_url` is a placeholder; verify play checks service unit presence and signing-key file perms. |
| **Ansible role: hysteria-realm** | ansible-lint | render check | **molecule** (converge + idempotence + verify) | sing-box tarball fetch gated on non-placeholder sha256; verify play checks realm-service unit + auth-token file perms. |
| **Ansible role: snell** | ansible-lint | render check + snapshots | **molecule** (converge + idempotence + verify) | RESEARCH-tier staging candidate; verifies the v5/v6 inbound matrix, secure config, pinned binary layout, and service health. |
| **Ansible role: split-hop-egress** | ansible-lint | render check | **molecule** (converge + idempotence + verify) | WireGuard peer config rendered from placeholder keys; verify play checks wg-quick unit and key file perms on Node B. |
| **Ansible role: split-hop-ingress** | ansible-lint | render check | **molecule** (converge + idempotence + verify) | Verifies Node A has no peer endpoint/keepalive and policy routing marks only new original-direction probe runtime flows. |
| **Ansible role: cascade-ingress** | ansible-lint + structural guard tests | render check + classifier/probe socket-process fixtures | **required paired molecule** (`populated` + `forced-empty`) | EXCEPTION-tier and absent from family profiles. Tests cover the RU/foreign interface-selection mapping, authenticated SOCKS boundary, IP-only handoff, startup/runtime dataset loss, DNS/WARP bypass prevention, authenticated leg/control health transitions, and redacted evidence. Molecule proves the adapter/probe units remain literally disabled; forced-empty must block before any unit, proxy secret, tunnel configuration, or serving state and is required independently from the happy path. |
| **Ansible role: cascade-egress** | ansible-lint + classifier-isolation test | render check | **molecule** (converge + idempotence + verify) | Owns only the private tunnel listener and forwarding scaffold; tests prohibit classifier/geodata knowledge and client-facing behavior. |
| **Ansible role: probe-matrix-target** | ansible-lint | render check | **molecule** (converge + idempotence + verify) | Verifies all five rendered listener configs, systemd hardening directives, and protected Xray, mtg, and TLS key files; service startup remains a live-staging gate. |
| **Ansible role: xray-runtime** | ansible-lint | n/a | covered by Xray and probe-matrix-target scenarios | One pinned installer shared by the family and research Xray services. |
| **Ansible role: runtime-release** | ansible-lint + 81 contract tests | n/a | isolated native root-Ansible acceptance (not Molecule) | Receipt-owned binary and archive staging, exact-pin publication, idempotence, upgrade links, failure cleanup, same-pin controller serialization, and foreign-replacement retention are exercised against the role. Consumer-specific Molecule coverage is added as each runtime migrates. |
| **Ansible role: reality-self-steal** | ansible-lint | render check + focused REALITY policy tests | **molecule** (default sequence: dependency, syntax, create, converge, idempotence, verify, destroy; disabled sequence: dependency, syntax, create, converge, verify, destroy) | Verifies the enabled and disabled configuration boundaries with synthetic local inputs. External target selection and filtered-path acceptance remain live checks. |
| **Ansible role: node_manifest** | ansible-lint | render check + snapshot | n/a | writes deterministic `/var/lib/ripdpi-vpn-deploy/manifest.json`; unit tests assert deployable source provenance, public listeners, and security-control fields stay non-secret and parseable. |
| **Ansible role: security_audit** | ansible-lint | render check | n/a | operator-run only through `make security-audit`; collects non-blocking reports under `/var/log/ripdpi-vpn-deploy/security-audit/`. |
| **Full stack** | ansible-lint | render check | **required hosted CI** runs full-stack sequence: dependency, syntax, create, prepare, converge, idempotence, verify, destroy; full-stack-published sequence: dependency, syntax, create, prepare, converge, idempotence, verify, destroy | Runs the entire `site.yml` end-to-end inside a privileged Debian-13 container with NET_ADMIN; `full-stack-published` remains separately runnable by an operator for published-listener checks. See `ansible/molecule/full-stack/`. |
| **Shell scripts (56)** | `bash -n` syntax + **`shellcheck -s bash -S warning`** (CI) | n/a | n/a | every shell script in `scripts/` runs through shellcheck; the two isolated exception-root boundaries are linted by the exception Terraform CI job. |
| **Python validators** | implicit — they validate everything else | n/a | n/a | |
| **Secrets schema** | **`scripts/check-secrets-coverage.py`** | n/a | n/a | Walks every Jinja2 template, ensures every top-level variable is declared in `secrets/prod.secrets.example.yaml`, `group_vars/all.yml`, or a role's `defaults/main.yml`. |
| **Jinja2 templates (112)** | **`scripts/check-templates-render.py`** | renders all 112 role templates against synthetic + example data | n/a | Catches Jinja syntax errors, JSON-invalid output for `*.json.j2`, nginx parse errors for site configs. |
| **Cohort group_vars** | render check (group_vars/all.yml + cohort file are merged into render env) | n/a | n/a | If a cohort file references a flag the role doesn't accept, render fails. |
| **YAML formatting** | **yamllint** (CI) | n/a | n/a | uses `.yamllint.yml` profile. |
| **GitHub automation security** | **zizmor 1.29.0** (`make zizmor-check` + required CI) | strict offline collection of owned workflows, actions, Dependabot, and pre-commit configuration | executable negative fixtures | The mise pin and checksum-verified CI binary run the same regular-persona gate; missing or mismatched local versions, unsupported output formats, actionable findings, and malformed owned YAML fail closed. The runtime contract also proves vendored nested workflows stay outside the explicit owned-input scope. |
| **Secret leak detection** | **gitleaks** with custom rules (CI + pre-commit) | n/a | n/a | Custom rules: VLESS/Trojan/Hysteria URIs, REALITY priv keys, WG priv keys, age-secret-key, subscription tokens. |
| **Placeholder leak** | **`scripts/pre-commit-placeholder-scan.py`** (pre-commit) | n/a | n/a | Rejects any staged file (outside the schema example + generator scripts) that carries a `REPLACE_WITH_*` token. |
| **Decrypted-secrets audit** | **`scripts/spot-check-secrets.py`** (gating `make deploy`/`verify`) | walks the decrypted YAML | n/a | Placeholder check, cert expiry, RSA modulus match, H1..H4 type, password length. Bypass with `SKIP_PRECHECK=1`. |
| **Cert hygiene** | **`scripts/check-certs.sh`** (gating `make deploy`/`verify`) | openssl-driven | n/a | SAN coverage, expiry < 14 days, self-signed detection, modulus match across nginx_xhttp / hysteria / naive. |
| **Pinned-binary reproducibility** | **`.github/workflows/reproducible-build.yml`** (CI) | go build + sha256 compare | n/a | Three jobs: xray (from-source rebuild → soft-warn on bytewise drift), hysteria (hard-fail on release-asset sha256 mismatch), RealiTLScanner (same). |
| **Real-VPS end-to-end** | **`.github/workflows/real-vps-deploy.yml`** (workflow_dispatch / `ci-real-deploy` label) | provision → site.yml → verify → destroy | n/a | Approximates production deploy as closely as Actions allows. Ephemeral UpCloud VPS per run. Does not currently run smoke-test. See `docs/CI-REAL-DEPLOY.md`. |
| **Real-VPS AWG/NAT data plane** | **`ripdpi-real-vps-awg-nat.timer`** (weekly local systemd; optional manual Actions workflow) | exact-source deploy → physical `amneziawg-go` client → TCP+UDP echo → observed restart → transactional PSK reload + old-key rejection → peer/NAT evidence → teardown | n/a | Dedicated self-hosted sentinel against an owner-controlled VPS. The local executor archives a root-owned exact-SHA checkout and retains redacted manifests without GitHub. The Actions executor is `workflow_dispatch`-only because its private runner is optional. Missing private runner state fails as `INFRA_UNAVAILABLE`; it never skips green. See `docs/CI-REAL-VPS-AWG-NAT.md`. |
| **Kill-switch validation** | **`scripts/check-singbox-killswitch.py`** (operator-driven) | static JSON analysis | n/a | Verifies auto_route + strict_route, route.final ≠ direct, DNS detour ≠ direct, no IPv6-only outbounds. |
| **sing-box client compatibility** | official sing-box 1.13.16 parser (sha256-pinned in CI) | complete emitted test profile | n/a | Rejects removed DNS/inbound fields and unsupported transports before a profile can ship. |
| **Sentinel profile compatibility** | official sing-box 1.13.16 and Xray 26.3.27 parsers (SHA256-verified assets in CI) | canonical emitters plus named-client materialization | `make liveness-profile-check` | Required by `ci-fast`; verifies REALITY/Hysteria2 and XHTTP syntax with real binaries. This is not external traffic or AWG/device acceptance. |
| **vpnd Rust crate (177 tests)** | `cargo clippy --release --all-targets -- -D warnings` (CI) | n/a | `cargo test --release --locked` (CI, blocking) | Covers runner builders (process, make, ansible, terraform, sops), config discovery, secrets parsing, registry round-trip, QR encode, update-cache, completions snapshot, ai-docs emit, host CRUD, doctor bundle, share bundle. Plus 4 proptest properties for `urlencode` round-trip and `redact_secrets` per-line invariants. |
| **vpnd mutation testing (weekly)** | `cargo mutants` (`.github/workflows/mutants.yml`) | n/a | n/a | Scheduled Monday 08:00 UTC. Targets `src/runner/**`, `src/commands/doctor.rs`, `src/pages/qr.rs`, `src/secrets.rs`. Non-blocking — surviving mutants posted to a rolling tracking issue with label `automation:mutation-testing`. |
| **Python tests (3256 collected)** | pytest (CI and local; 3203 under `tests/unit/`) | n/a | n/a | Covers emit-singbox, SOPS round-trip, render-inventory including custom SSH ports, replacement safety, Vultr control-plane preflight and guest IPv4 convergence, rolling OS maintenance and recurring security-update policy, relay/fallback, subscription token revocation lifecycle, client registry refresh/drift contracts, probe-matrix drivers/contracts/provisioning, cascade attestation freshness, tri-state per-connection classification, authenticated per-leg probe state and health freshness, inert Terraform and role/profile guards, in-cohort rule-drift canary classification, Snell refinement classification, singbox kill-switch, policy-ratelimit ban logic, burn-check error metrics, listener-collision guard, node manifest source parity, receipt-owned transactional runtime releases and serialized publication, crash-recoverable source-build write-ahead journals, AmneziaWG check-mode build receipts and arm64 version-floor tracking, recurring real-VPS AWG/NAT source binding, generation transitions, transactional rotation, cleanup, and fail-closed evidence, cloud-init completion and restart acceptance, deployment profiles, strict live-inventory and extra-vars gates, injected-fact removal, watchdog bounded recovery, Xray StatsService and redacted exporter contracts, check-mode-safe service handlers, restricted Tailnet enrollment and deploy-controller credential isolation, Molecule dependency-path and driver-pin guards, honeypot log retention, calendar-window metrics, dual-stack binding, public-site behavior, P1 node-local hostname resolution, XHTTP-only backend rendering, REALITY self-steal contracts, repository symlink scanning, and protocol-liveness evaluation, sentinel cleanup, onboarding, and OTP rotation gates. (Shell orchestrator dry-runs migrated to bats — see below.) |
| **Shell-orchestrator bats tests (55 tests)** | `bats tests/bats/` (CI, blocking) | n/a | n/a | Covers `blue-green.sh --dry-run`, `fleet-rotate.sh --dry-run`, `age-recovery-combine.sh` 3-of-5 round-trip, `restore.sh --dry-run` (path-A + path-B including secrets-before-playbook ordering), operator cron rendering, and atomic optional Snell client updates. Uses the same `tests/stubs/bin/` PATH-prepend harness as the Python tests. bats-support v0.3.0 + bats-assert v2.1.0 vendored under `tests/bats/test_helper/`. |
| **Terraform policy (cross-provider, Conftest)** | `.github/workflows/tf-policy.yml` per PR | n/a | n/a | Runs each provider's native Terraform tests with `mock_provider`, then `conftest verify --rego-version v0 -p terraform/policy/` for Rego syntax/unit-test validation. The workflow intentionally does not run real provider plans against example tfvars because those require operator credentials and provider API access. `make tf-policy` for local; pinned Conftest 0.57.0 is mandatory for `make ci-fast` and `make check` (see `mise.toml`). |
| **Container image scanning (Trivy)** | `.github/workflows/image-scan.yml` per PR | n/a | n/a | Every PR scans the complete deduplicated set of digest-pinned images from all Molecule scenarios, independent of changed paths. Uploads HIGH/CRITICAL SARIF to the Security tab. Escalate only with rationale + expiry + owner in `.trivyignore`. |
| **Repo drift (weekly)** | `.github/workflows/drift.yml` | `scripts/drift-since-tag.sh --repo-only` | n/a | Scheduled Monday 12:00 UTC. Diffs the repository against the last known-good tag. Updates a single rolling issue labelled `automation:drift` when drift is detected; silent when clean. Operator-side cron (against live servers) is unchanged and uses the script without `--repo-only`. |
| **Task and OpenSpec contract** | `make task-check` + required `task-contract` CI job | strict portfolio, mdtask, OpenSpec, generated-asset, board, and deletion-history validation | peer checkout in CI | Federation resolves qualified RIPDPI task references, terminal Git history, and cross-repository cycles. |
| **Jinja2 snapshot diff (112 templates)** | `scripts/render-snapshots.py` | golden-file diff | n/a | Fails on any unintended render change. Run `make snapshot-update` after intentional template edits. |

## Test fixtures and stubs

All shared test inputs live under `tests/fixtures/` and stub binaries under
`tests/stubs/bin/`.

### `tests/fixtures/`

| File | Purpose |
|---|---|
| `secrets-sample.yml` | SOPS-decrypted-shaped YAML with placeholder values; loaded by pytest and Rust integration tests via `include_str!` |
| `secrets-sample.sops.yaml` | Same content age-encrypted to a test-only key (`tests/fixtures/age-test.key`) |
| `tf-output-sample.json` | `terraform output -json` shape; consumed by render-inventory tests |
| `inventory-sample.ini` | Expected output of `render-inventory.sh` for the sample TF output |
| `fleet-plan-sample.yaml` | Input shape for `fleet-rotate.sh --dry-run` tests |
| `age-recovery-shares/` | 5 Shamir shares (3-of-5 threshold) for age-recovery round-trip tests |
| `singbox-killswitch-valid.json` | Valid sing-box bundle for kill-switch positive-case test |
| `xray-access-sample.log` | Real-shaped Xray v26.3.27 access-log lines (benign + blackholed + rejected) for the policy-ratelimit ban-logic test |
| `xray-error-sample.log` | Real-shaped Xray error-log REALITY probe lines (`processed invalid connection`); proves the daemon cannot ban external probers |

### `tests/stubs/bin/`

POSIX shell scripts (shellcheck-clean, ≤30 lines each) that replace real
binaries during pytest dry-run tests. Tests prepend `tests/stubs/bin` to
`PATH`; each stub echoes its invocation to `$STUB_LOG` so tests can assert
exact argument vectors without network or filesystem side-effects.

Stubs provided: `terraform`, `ansible-playbook`, `sops`, `curl`, `gh`,
`upcloud`, `hcloud`, `vultr`.

The bats tests under `tests/bats/` use the same `PATH=tests/stubs/bin:$PATH`
discipline and call the same fixture files. See `tests/stubs/README.md` for
the discipline contract and how to add a new stub.

## Test phases mapped to operator workflow

Backup configuration regressions require a real `restic` executable on `PATH`
(validated with 0.16.4 and 0.18.0). CI installs it with the existing unit-test
system packages. These tests initialize only private temporary repositories and
exercise `--no-cache --no-lock cat config` with valid, wrong-password, and damaged
configuration inputs; a missing binary is a failure, not a skip. The separate
backup Molecule scenario is required to prove systemd/package behavior on Linux.

| Operator step | Tests that protect it |
|---|---|
| `git commit` (local) | pre-commit hooks: gitleaks, terraform fmt, ansible-lint, yamllint, **shellcheck**, **secrets-coverage**, **templates-render**, **Xray release/PQ-REALITY guards**, **placeholder-scan** |
| `git push` (PR) | CI matrix: terraform fmt+validate (4 providers plus the inert exception root), terraform test (4 providers), cloud-init schema, ansible-lint + syntax, default Molecule scenarios for `baseline`, `firewall`, `network-exposure-gate`, `tailnet-management`, `xray`, `hysteria`, `nginx-xhttp`, `watchdog`, `monitoring`, `observability_agent`, `observability_control_plane`, `backup`, `subscription-host`, `amneziawg`, `geodata`, `cascade-egress`, `cdn-front`, `warp-outbound`, `hysteria-realm`, `honeypot`, `dns-morph-bridge`, and `split-hop-egress`; required hosted full-stack scenarios `full-stack`, `full-stack-published`; non-default scenarios `watchdog/failure`, `observability_agent/enabled`, `observability_control_plane/enabled`, `cascade-ingress/populated`, `cascade-ingress/forced-empty`, and `hysteria-realm/shared-tls`; shellcheck, secrets-coverage, templates-render, yamllint, gitleaks, strict offline zizmor, `pytest tests/unit/` (live collection count recorded above), Rust tests, bats tests, Conftest TF policy, Trivy image scan, snapshot diff, and secrets schema. |
| PR labeled `ci-real-deploy` | **real-vps-deploy** workflow: provisions an ephemeral UpCloud VPS, runs site.yml + verify, destroys — closest approximation to production in CI. See `docs/CI-REAL-DEPLOY.md`. |
| `make validate` (operator) | terraform fmt + validate + gitleaks + ansible-lint + ansible syntax-check |
| `make ci-fast` (operator) | Portable credential-free CI jobs: actionlint, strict offline zizmor, cloud-init schema, all provider Terraform tests and Conftest policy tests, yamllint, shellcheck, cargo-deny, MSRV, render/schema/unit/bats, clippy, and Rust tests. Missing or wrong-version tools fail closed. |
| `make check` (operator) | Union of `validate` and `ci-fast`; the local pre-PR parity gate. Molecule, GitHub-native security services, and credentialed deploy jobs remain explicit or CI-only. |
| `make validate-target` | live probe of REALITY target (TLS / H2 / SAN / uTLS / ASN / template OPSEC) |
| `make monitor-reality-target VANTAGE=<technical-label>` | filtered-vantage active-target path and ASN/prefix signal; unhealthy observations on two consecutive UTC days alert |
| `make plan` | terraform plan (catches infrastructure drift) |
| `make dry-run` / `make deploy` / `make verify` | **pre-deploy-check** runs first: spot-check-secrets + check-certs; bypass with `SKIP_PRECHECK=1` |
| `make deploy-canary` | same deploy path as `make deploy`, with `ENV=canary` forced by the Makefile wrapper |
| `make deploy` | role handlers run validate-before-restart (Xray, nftables, nginx) |
| `make verify [TAG_ON_SUCCESS=1]` | post-deploy gates assert services up, listeners present; optionally git-tag the commit as `vpn-deploy-known-good-*` |
| `make security-verify` | post-deploy host-hardening gates for SSH, sysctl, firewall egress policy, package updates, Fail2Ban, and manifest presence |
| `make security-audit` | operator-run, non-blocking audit report collection; intentionally not part of deploy or verify gates by default |
| `make drift-since-tag` | weekly: diff fleet against the last known-good tag (terraform plan + ansible --check). The CI scheduled variant uses `--repo-only` and runs without SOPS access — see `.github/workflows/drift.yml`. |
| `make source-drift` | fast fail-closed comparison of the clean checkout's deployable digest with every live node manifest; also runs automatically after `make deploy` and `make verify`. |
| scheduled Monday 08:00 UTC | **cargo-mutants** (`.github/workflows/mutants.yml`) — validates vpnd test suite is doing its job; non-blocking |

The repository-safe record of the last observed production deployment is
[DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md). It distinguishes provider-live
Terraform refresh, configuration-to-state comparison, Ansible convergence,
host verification, and outside-in client-path evidence. At `infra-v1.0.0`,
`make dry-run` also has a documented check-mode-only firewall discovery
failure; a live deploy does not turn that false failure into a passing test.
| scheduled Monday 12:00 UTC | **drift-since-tag --repo-only** (`.github/workflows/drift.yml`) — repository-level drift detection; opens/updates a rolling issue |
| scheduled Monday 10:23 UTC | **AmneziaWG arm64 floor watch** (`.github/workflows/amneziawg-arm64-floor.yml`) — flags issue-state or release-note fix claims for physical revalidation; never relaxes guards |
| weekly weekend | **Renovate** opens dependency-update PRs for supported managers, including grouped Terraform providers and Rust crates, GitHub Actions digest pins, and Hysteria Realm / Snell sing-box pins via regex managers. |
| `make smoke-test` | end-to-end real-traffic dial through every enabled profile |
| `make check-killswitch BUNDLE=…` | per-client validation of emitted sing-box bundle (5 rules: auto_route, strict_route, sniff, final ≠ direct, DNS detour ≠ direct, no IPv6-only outbound) |

## Dependency updates

Renovate opens weekly PRs for the ecosystems it supports, and each PR runs
through the full CI matrix above before a human merges. Xray and AmneziaWG
remain manual, policy-gated updates because their pins cannot be updated safely
and completely by the current regex managers.

Renovate config lives at `renovate.json` at the repo root. Key behaviors:

- `helpers:pinGitHubActionDigests` preset — every Action stays SHA-pinned;
  Renovate auto-updates digests with the matching version comment preserved.
- Terraform providers grouped into a single weekly PR; Rust crates grouped
  the same way (lowers merge overhead).
- Custom regex managers cover only the Hysteria Realm and Snell sing-box
  version pins. Xray follows `docs/XRAY-RELEASE-LINE.md`; AmneziaWG follows
  the arm64 floor-watch workflow and both require manual updates.
- `vulnerabilityAlerts.enabled: true`. Schedule: weekly on weekends.

| Ecosystem | Renovate covers? | Where pinned | Refresh cadence |
|---|---|---|---|
| GitHub Actions (digests) | yes | `.github/workflows/*.yml` | weekly, one PR per Action |
| Terraform providers | yes | `terraform/providers/*/versions.tf` + `.terraform.lock.hcl` | weekly, grouped |
| Rust crates | yes | `vpnd/Cargo.toml` + `vpnd/Cargo.lock` | weekly, grouped |
| Python tooling | yes | `requirements.txt` | weekly, grouped |
| Hysteria Realm / Snell sing-box binaries | yes (via regex managers) | role defaults | per upstream release; human review required |
| Xray / AmneziaWG binaries | **no** | secrets/example pin and role defaults | manual, after release-policy and platform validation |
| Ansible Galaxy collections | **no** (Renovate gap) | exact versions in `requirements.yml` | manual quarterly review (see below) |
| geodata (geosite/geoip) | n/a | concrete URLs + sha256 values in the deployed vars file | daily systemd timer on the VPS via `geodata` role |

### Manual quarterly Galaxy collection refresh

Renovate does not yet support Ansible Galaxy. Once a quarter, run:

```bash
# Inspect current pins
grep -A1 'name:' requirements.yml

# Check upstream for newer versions
ansible-galaxy collection list  # local cache
# or browse https://galaxy.ansible.com/<collection>

# Bump exact pins in requirements.yml; install fresh
rm -rf ~/.ansible/collections
ansible-galaxy collection install -r requirements.yml --force

# Re-run molecule on at least one role
make molecule-test ROLE=baseline

# Commit with: chore(deps): refresh Ansible Galaxy collections
```

Auto-merge is intentionally **not** enabled for any Renovate PR — every
update goes through a human review. Operators who want auto-merge can
configure it per-ecosystem in repo Settings.

## Build attestation (SLSA Level 3)

Every released `vpnd` binary ships with a Sigstore-signed SLSA-v1.0 Build
Level 3 provenance attestation generated by `actions/attest-build-provenance`
from `.github/workflows/release-vpnd.yml`. The attestation proves the binary
came from this repo's trusted build workflow on a specific commit SHA.

Verify a downloaded binary:

```bash
gh attestation verify ./vpnd-x86_64-unknown-linux-gnu \
  --owner po4yka --signer-workflow .github/workflows/release-vpnd.yml
```

`scripts/install-vpnd.sh` calls this automatically when `gh` is on PATH and
`VPND_SKIP_ATTESTATION` is unset. The script warns and continues if `gh` is
missing — set `VPND_SKIP_ATTESTATION=1` to opt out explicitly.

## External reachability (post-deploy, operator-side)

| Surface | Probe | Vantage | Notes |
|---|---|---|---|
| **TCP/443 (REALITY)** | `make burn-check` via check-host.net nodes | RU + EU third-party | Exits non-zero when ≥`FAIL_THRESHOLD` vantages can't connect — the IP-burn signal. |
| **UDP/443 (Hysteria2/QUIC)** | `make burn-check` QUIC Version-Negotiation probe | operator workstation | **Always non-fatal (WARN).** Sends an unauthenticated QUIC long-header packet with a `0x?a?a?a?a` force-VN version, padded to QUIC's 1200-byte minimum; any reply proves UDP/443 was delivered end-to-end. Skips (WARN) when `ENABLE_HYSTERIA=false` or `HYSTERIA_SALAMANDER=true` (obfs makes external blackbox probing impossible). Exports `vpn_burn_udp_reachable`. |

When `NODE_EXPORTER_TEXTFILE_DIR` is set, burn-check refreshes
`vpn_burn.prom` on every exit. `vpn_burn_api_error=1` identifies an external
API failure and `vpn_burn_run_error=1` identifies a run that ended before a
reachability classification. Incomplete runs omit stale per-node and summary
reachability series.

**Why on-host UDP checks are insufficient.** Several cloud providers silently
drop inbound UDP/443 at the **provider-edge** firewall even when the instance's
own `nftables` shows ACCEPT and the listener is bound (`ss -ulnp` correct). The
instance kernel cannot see that layer, so a server-side or molecule check can
never detect the gap — it must be probed from outside the data center. Diagnostic
rule: trust `tcpdump` showing inbound packets, not `nft list` showing ACCEPT. If
the burn-check UDP probe gets no reply, `tcpdump -i any udp port 443` on the
server disambiguates a provider-edge drop (zero inbound) from server-side silence
(packets present). See `docs/PROVIDER-NOTES.md` → "UDP/443 edge reachability".

## Pre-commit hooks

Local pre-commit configuration (`.pre-commit-config.yaml`) catches common
issues before CI cycles:

- `task-contract` — validates portfolio records, mdtask execution, OpenSpec,
  generated assets, board freshness, and terminal-history rules.
- `terraform_fmt`, `terraform_docs`, `terraform_tflint` via
  `antonbabenko/pre-commit-terraform` — Terraform formatting, auto-generated
  per-provider README, and security linting.
- `cargo-clippy` (local hook) — workspace warnings-as-errors for vpnd.
- `prettier` scoped to JSON files in `tests/fixtures/` and `secrets/schema.json`
  only — does not touch markdown or vendored package.json files.

Generated `terraform/providers/<name>/README.md` files are committed; the
`terraform_docs` hook keeps them in sync on every commit.

## What is intentionally NOT tested

- **Live external network reachability of upstream geodata / Xray / Hysteria
  binaries.** Test would couple the build to upstream availability. We
  pin-and-checksum at deploy; CI doesn't re-validate every release.
- **AmneziaWG TUN converge inside Docker.** Requires kernel TUN device +
  golang build of amneziawg-go. Render check covers template correctness;
  `awg show` is part of `verify.yml` against a real VPS.
- **NaiveProxy xcaddy build.** Pulls Go modules; flaky in CI. Render check
  + bash-syntax cover the artifact shape; the build runs only on the target
  VPS during deploy.
- **Cloudflare WARP registration.** Requires a registerable WARP endpoint not
  available in CI containers. Structure validation only via molecule
  syntax-only scenario.
- **RealiTLScanner full-scan integration.** Binary required at runtime;
  coupling CI to upstream build would introduce flakiness. Shellcheck covers
  the wrapper script shape.
- **`scripts/restore.sh` real mode.** The `--dry-run` mode is covered by
  `tests/unit/test_restore_dryrun.py`. The live restore path (decrypts
  SOPS secrets, re-provisions real infrastructure) is only safe to exercise
  against a throwaway VPS; a maintainer TODO covers adding it to the
  `ci-real-deploy` label workflow.
- **End-to-end traffic against geographic locations** (RU, EU, US). Would
  require live infrastructure with the right BGP. This is what
  `make burn-check` (operator-side cron) covers post-deploy — including the
  external UDP/443 edge-reachability probe (see "External reachability" above).
- **Long-running stability** (memory leaks, descriptor exhaustion). Out of
  scope for unit-level testing; the watchdog role catches it post-deploy.
- **Active-probing simulation** against the deployed REALITY listener. The
  validator covers the static OPSEC properties; behavior under real
  probing is observable only against live infrastructure. Note: the
  `policy-ratelimit` daemon does **not** detect external REALITY probes by
  design — `xtls/reality`'s `func Server` proxies failed-auth probes to the
  camouflage `Dest` ("steal-oneself") and surfaces only a returned
  `fmt.Errorf` logged at `[Info]` to error.log (suppressed at
  `loglevel: "warning"`), never to the access.log the daemon tails. The daemon
  rate-limits policy-violating egress (blackholed + VLESS-rejected traffic)
  instead; `tests/unit/test_policy_ratelimit.py` asserts both the enforceable
  bans and the prober-invisibility. The role README carries the full ADR (path
  (b): no nginx-stream front). See
  `ansible/roles/policy-ratelimit/README.md`.

## Adding a new role

When you add a role, the checklist is:

1. Write the role under `ansible/roles/<name>/`.
2. Reference it in `ansible/playbooks/site.yml` with a `vpn.enable_<name>`
   toggle.
3. Add the toggle to `ansible/group_vars/all.yml` and to every
   `vpn-<cohort>.yml`.
4. If the role consumes new secret keys, add them to
   `secrets/prod.secrets.example.yaml`. **Do not skip this.** The
   `check-secrets-coverage.py` validator will fail PRs that miss it.
5. Either:
   - Add `ansible/roles/<name>/molecule/default/{molecule,converge,verify}.yml`
     and add the role to the molecule matrix in `.github/workflows/ci.yml`, or
   - Document a justified skip in this file's coverage matrix.
6. If the role drops shell scripts via templates, the rendered output must
   pass `bash -n` (added to your verify play).

## Adding a new template

1. Reference variables that exist in role defaults, group_vars, or the
   secrets schema. The `check-secrets-coverage.py` validator will catch
   omissions.
2. If it's a `*.json.j2` template, the render check will validate it as
   JSON.
3. If it's an nginx site config, name it `*.conf.j2` under a role whose
   parent dir contains "nginx" — the render check will run `nginx -t`.

## Adding a new script

1. `bash -n` must pass (catches syntax).
2. `shellcheck -s bash -S warning` must pass (catches common bash
   pitfalls). Add `# shellcheck disable=SCXXXX  # reason` for justified
   exceptions.
3. Include a top-of-file comment block describing usage, env, and exit
   codes.
