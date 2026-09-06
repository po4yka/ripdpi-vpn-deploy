# tests — coverage matrix

## Layers

| Layer | What | Where | Speed |
|-------|------|-------|-------|
| Unit | Python validators + Jinja-render assertions | `tests/unit/` (pytest) | seconds |
| Snapshot | Golden Jinja renders for every template | `tests/snapshot/` | seconds |
| Schema | `validate-secrets.py` jsonschema | `tests/unit/test_schema.py` | seconds |
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

**Client configs need an upstream parser gate** — CI installs a sha256-pinned
official sing-box binary and checks the complete standard emitter output.
Shape-only assertions supplement this gate; they do not replace it.

**Xray CI consumers share one verified installer** — template and sentinel
validation use `.github/actions/install-xray`. Keep its version/archive hash
together and aligned with the example version. Verify before extracting or
executing; install the runtime and its bundled geodata together after its
version command succeeds. Template routing rules need the adjacent data files.

**Molecule per role > monolithic test** — role-level scenarios catch
config drift inside a role. Full-stack catches order/handler interactions.

## What's done well

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
- **`validate-secrets.py` runs against the **schema**, not your real
  secrets** — by design. Strict mode (`--strict`) loads `SECRETS_FILE`
  and is operator-only.
- **Don't snapshot the diff of binaries** — QR PNGs, restic repos, etc.
  Snapshot the inputs, render the binary fresh, hash-assert if needed.
