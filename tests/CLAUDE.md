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
| CI ephemeral deploy | Label-gated real UpCloud deploy | `.github/workflows/` + `docs/how-to/ci-real-deploy.md` | ~15 min |

## Design decisions

Per-area decisions (native lanes, AWG, REALITY, monitoring, recovery, delivery and so on) live in [DESIGN-NOTES.md](DESIGN-NOTES.md). Before you change tests in an area, search that file for the area or test name and read only the matching paragraphs.

**`ci-fast` is the portable pre-PR gate** — runs the credential-free required
CI checks, including workflow/YAML/shell lint, cloud-init schema, all Terraform
tests, pytest/bats, Go helper integration, and vpnd Python tests, lint/type
checks, baseline parity, packages and dependency policy. `make check` adds
`task-check`, Terraform fmt/validate, gitleaks, and ansible-lint. Native Linux runtime integration, Molecule, GitHub-native
security services, and credentialed deploy jobs remain CI-only or explicit.

**Snapshots, not mocks, for templates** — `tests/snapshot/golden/` holds
the expected output of every Jinja render against fixtures. Drift is
visible in PR diffs.

**Pytest groups use measured durations** — four `pytest-split` groups share a
committed Linux profile. Keep `pytest unit tests` as the required aggregate: it
checks identical collections/profiles, disjoint selections and full execution.
Refresh the profile from the verified artifact; local `test-unit` stays complete.
Give clock-dependent parameter values stable IDs so collection agrees across runners.
Local and CI groups run under pytest-xdist with `--dist loadfile` (`PYTEST_WORKERS`,
default `auto`); the shard report receives the worker collection through
`workeroutput`. A fixed loopback port or a shared path outside `tmp_path` must stay
inside one module; a collision across modules is a test defect.

**CI selection follows complete consumers** — common Python/static checks always
run; costly PR lanes follow the selector's path graph. Docs are bundled into
Python vpnd. Keep Ansible scenarios together for cross-role inputs, and full CI for
manual/shared/unknown changes. A main push runs only the always-run checks when it
reuses a full successful PR run of the same tree (see the selector docstring);
any uncertainty keeps full CI. A portable-only `tests/unit/test_*.py` edit skips
native lanes only when no native lane selects, names or imports that module, and
such modules must not change process state at import time. The final gate requires every selected job
and permits only planned skips; adding a job must update the selector and tests.

**The documentation tree is a tested contract** — `test_docs_index.py` requires
every page under `docs/` (outside `tasks/`, `demo/` and `measurements/`) to be
listed in `docs/README.md`, to open with the status line from `docs/STYLE.md`
whose type matches its folder, to use a kebab-case or numbered-decision file
name, and to carry no geographic, carrier or censorship-apparatus label in its
name or headings. It also resolves every relative link in the tree and the root
README, CONTRIBUTING and AGENTS files against the Git index, so an untracked
target or a moved page fails here before lychee runs in CI.
`test_docs_reference.py` runs `scripts/docs-reference.py --check`, so the
Make-target reference, the vpnd command reference and `docs/llms.txt` fail
when their sources changed without `make docs-reference`.

**Coverage claims follow contracts** — `test_governance_counts.py` checks that
`docs/reference/testing.md` has a row per role and lists the hosted Molecule
scenarios CI runs, and that every Molecule image is digest-pinned. It pins no
counts or prose. Suite sizes come from runner output for a specific revision.

## Pitfalls

- **Selected skips fail required pytest lanes** — portable tests use
  `make test-unit` (both `tests/unit/` and `scripts/tests/`);
  `native_runtime` tests run separately with pinned
  Terraform/Alertmanager and UID/GID capabilities on a disposable Linux runner.
  Both use `--fail-on-skip`. Never run the full workstation suite as root.
- Pytest module basenames must be unique across `tests/unit`, `scripts/tests` and
  `vpnd/tests`: the full collection and shard-consistency checks import them together.
- **Snapshot files are committed** — never gitignore `tests/snapshot/golden/`.
  PR diff is the review surface.
- **Molecule needs Docker** — CI runners and operator workstations vary.
  Failing-to-find-docker is a setup error, not a test failure; the harness
  surfaces it explicitly.
- **State-changing test calls precede assertions** — capture retirement or
  retry results first, then assert them so optimized Python cannot omit the call.
- Set fault-injection permissions explicitly when rejection depends on mode; restrictive CI umasks can otherwise create a safe node instead of the intended unsafe fixture.
- **`validate-secrets.py` runs against the **schema**, not your real
  secrets** — by design. Strict mode (`--strict`) loads `VPN_SECRETS_FILE`
  and is operator-only.
