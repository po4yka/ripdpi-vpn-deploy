# tests — coverage matrix

## Layers

| Layer | What | Where | Speed |
|-------|------|-------|-------|
| Unit | Python validators + Jinja-render assertions | `tests/unit/` (pytest) | seconds |
| Snapshot | Golden Jinja renders for every template | `tests/snapshot/` | seconds |
| Schema | `validate-secrets.py` jsonschema | `tests/unit/test_secrets_schema.py` | seconds |
| Molecule (role) | Per-role Ansible scenario in Docker | `ansible/roles/<role>/molecule/` | ~1 min/role |
| Molecule (full-stack) | `site.yml` end-to-end | `ansible/molecule/full-stack/` | ~10 min |
| TF test | `mock_provider` plan-shape tests | per `terraform/providers/<name>/` | seconds |
| CI ephemeral deploy | Label-gated real UpCloud deploy | `.github/workflows/` + `docs/CI-REAL-DEPLOY.md` | ~15 min |

## Design decisions

**`ci-fast` is the portable pre-PR gate** — runs the credential-free required
CI checks, including workflow/YAML/shell lint, cloud-init schema, all Terraform
tests, pytest/bats, cargo-deny, MSRV, clippy, and Rust tests. `make check` adds
Terraform fmt/validate, gitleaks, and ansible-lint. Native Linux runtime integration, Molecule, GitHub-native
security services, and credentialed deploy jobs remain CI-only or explicit.

**Snapshots, not mocks, for templates** — `tests/snapshot/golden/` holds
the expected output of every Jinja render against fixtures. Drift is
visible in PR diffs.
Role-render tests reuse `scripts/template_render.py` for named-template escaping
and Ansible filters. Local HTTPS fixtures explicitly require TLS 1.2 or newer.

**Client configs need an upstream parser gate** — CI installs a sha256-pinned
official sing-box binary and checks the complete standard emitter output.
Shape-only assertions supplement this gate; they do not replace it.

**Xray CI consumers share one verified installer** — template and sentinel
validation use `.github/actions/install-xray`. Keep its version/archive hash
together and aligned with the example version. Verify before extracting or
executing; install the runtime and its bundled geodata together after its
version command succeeds. Template routing rules need the adjacent data files.

**Pytest groups use measured durations** — four `pytest-split` groups share a
committed Linux profile. Keep `pytest unit tests` as the required aggregate: it
checks identical collections/profiles, disjoint selections and full execution.
Refresh the profile from the verified artifact; local `test-unit` stays complete.
Give clock-dependent parameter values stable IDs so collection agrees across runners.

**Promotion proof covers aliased temp roots** — the controller's snapshots
must reach the evaluator through canonical private paths even when the OS
returns a symlinked temporary root.
Provider promotion tests include an instruction symlink and generated cache in
`terraform/shared`; they must be ignored while the required shared inputs stay
regular, pinned files. A non-default workspace test also checks that Terraform's
first directory setup cannot violate the private snapshot mode floor.
Public-listener verifier fixtures use literal source addresses or complete
named-set objects; a dangling `@set` reference is intentionally rejected.
Disposable de-onboarding tests also exercise a reissued cleanup manifest after
firewall promotion and reject a foreign server UUID before any local deletion.
Disposable de-onboarding fixtures use the current UpCloud schema-3 absence
receipt and reject an obsolete version before mutation. Its registry fixture
uses the installer's exact sorted JSON format.
Unbound-retirement fixtures must start with registered pre-destroy state and
then write different empty state. Exercise copied/inode-replaced authority,
unclaimed absence and post-destroy state replacement before SOPS publication.
Prepared-executor tests require a completed real client retirement transaction,
profile marker/configuration/context guards, assignment races and interrupted
stop/delete retry; fixture success remains source evidence only.
Exercise real SOPS retirement both with and without optional Snell collections;
an absent section is valid, while malformed or partial configured state refuses.

**Disposable observability acceptance is evidence-class strict** — focused
schema-2 tests cover co-hosted VPN capabilities, one collector, independent
Kuma placement, exact push-monitor bindings and rejection of old host classes.
PKI tests exercise real OpenSSL IP-SAN verification, scoped revocation and SOPS
encryption/decryption, including strict certificate-chain checks with explicit
key identifiers. Refresh the encrypted synthetic fixture whenever its plaintext
counterpart changes. Tests that isolate HOME need real SOPS on PATH, not a
version-manager shim whose trust state depends on the original home directory.
Real pinned Kuma runtime timing is separate from mocked
push or Telegram tests; no synthetic receipt proves human notification.
Sender replacement checks use the actual pinned vmagent parser and persistent
queue behavior. Clean and abrupt restart evidence must query pre-restart sample
timestamps at the collector; queue files, empty buffers and fresh samples alone
cannot pass. Byte/block drop counters are not interchangeable with sample counts.
Historical dedicated-host
selector tests prove staging-only enablement, disabled production, required
explicit secret scope, and mixed-scope refusal before Terraform or publication.
The old global boolean must fail, not become an implicit compatibility path.
Focused
unit tests keep the fixed staging row order, exact-host and private-file
boundaries, real one-hour critical reminder program, interruption restoration,
durable receipt reconciliation, human-observation gate, complete-set cleanup
plans, provider-specific absence and redacted terminal schemas separate. The
rollback tests distinguish retained last-known-good inputs from the active
candidate, and invalid-candidate credit requires an exact one-field mutation
plus the typed first role-guard failure; another Ansible failure is never
accepted. Typed-refusal capture tests enforce the fixed 64 KiB streaming cap,
redacted failure, deadline, and owned-process cleanup. Authenticated negative
ingestion probes require an explicit HTTP
status while only plaintext and missing-identity TLS probes accept transport
refusal. The
local input preparer is contract-locked to that row order and proves no-clobber
private roots, fail-closed draft approvals/bindings, schema-valid SOPS runtime
fragments, secure sticky-only writable ancestry, descriptor-bound refusal on
root substitution, and real OpenSSL certificate purposes without provider or
Telegram access. A
fixture executor or synthetic HTTP status is source evidence only; it never
marks a live Telegram or provider action complete.

**Molecule per role > monolithic test** — role-level scenarios catch
config drift inside a role. Full-stack catches order/handler interactions.
The two full-stack scenarios run on separate matrix runners with fail-fast
disabled; `required checks` requires both to succeed.
Tailnet role Molecule also asks the real `systemd-analyze` in a PID 1 container
to parse the complete recovery/SSH dependency graph and fails on diagnostics
even when `verify` returns zero. This is static graph evidence only: its inert
`tailscaled.service` fixture is not vendor-unit, activation, or reboot evidence.
Its native OpenSSH check hides `/run` in a private mount namespace, requires
the real `-T` runtime refusal, and compares complete cold `-G` policy with
the ordinary dump and warm `-T` output. Preparation must not create `/run/sshd`.

**CI Python tooling shares one cached setup** — `setup-ci-python` always checks
hash-pinned requirements, even on a pip cache hit. Galaxy consumers set the same
absolute `ANSIBLE_COLLECTIONS_PATH` as the action's isolated collection cache.
OS, architecture, Python and both requirements files determine its exact key.
The `python validators` job preserves seven checks behind one required context.

**CI selection follows complete consumers** — common Python/static checks always
run; costly PR lanes follow the selector's path graph. Docs are compiled into
Rust. Keep Ansible scenarios together for cross-role inputs, and full CI for
main/manual/shared/unknown changes. The final gate requires every selected job
and permits only planned skips; adding a job must update the selector and tests.

**Cloud-init schema uses Ubuntu package sources only** — its installer selects
the runner's `ubuntu.sources` for both APT operations. An unrelated preinstalled
repository cannot block this gate. Missing Ubuntu sources and failed updates
remain fatal; package signatures and the real schema validator stay enforced.

## What's done well

- **Provider example parity is checked** — every explicit staging/prod listener
  example includes the default nginx HTTP redirect, so a copied environment
  reaches the same fail-closed runtime contract as the provider roots.

- **Quirk-named tests** — `test_xhttp_path_matches_both_slash_and_unslashed`,
  `test_relay_sni_fails_closed_when_local_sni_missing`. The name *is* the
  doc.
- **`snapshot-update` is explicit** — never updates on assertion failure;
  requires an operator running `make snapshot-update` after an intentional
  template change. CI never auto-updates.
- **`shellcheck` in CI** — every `.sh` file. Warnings break the build.

## Pitfalls

- **Selected skips fail required pytest lanes** — portable tests use
  `make test-unit` (both `tests/unit/` and `scripts/tests/`); four
  `native_runtime` tests run separately with pinned
  Terraform/Alertmanager and UID/GID capabilities on a disposable Linux runner.
  Both use `--fail-on-skip`. Never run the full workstation suite as root.
- **Compiled helper coverage is real Go execution** — `ci-fast` includes
  `make test-probe-matrix-mtproto`; Python driver tests cannot replace it.

- **Release SBOM is the locked Cargo inventory** — CI and publication share
  `.github/actions/vpnd-sbom`, which stages `dist/sbom.json`. The deployment
  example emitter serves `make emit-sbom` and is not the vpnd release SBOM.

- **Mutation CI distinguishes findings from execution failure** — only exit
  0 (caught) and 2 (survivors reported) are successful runs. The runtime tests
  exercise actual workflow shell error propagation and disposable-copy cleanup;
  real cargo-mutants baseline and mutation execution remain the acceptance gate.

- **Snapshot files are committed** — never gitignore `tests/snapshot/golden/`.
  PR diff is the review surface.
- **Molecule needs Docker** — CI runners and operator workstations vary.
  Failing-to-find-docker is a setup error, not a test failure; the harness
  surfaces it explicitly.
- **State-changing test calls precede assertions** — capture retirement or
  retry results first, then assert them so optimized Python cannot omit the call.
- **`validate-secrets.py` runs against the **schema**, not your real
  secrets** — by design. Strict mode (`--strict`) loads `VPN_SECRETS_FILE`
  and is operator-only.
- **Don't snapshot the diff of binaries** — QR PNGs, restic repos, etc.
  Snapshot the inputs, render the binary fresh, hash-assert if needed.
