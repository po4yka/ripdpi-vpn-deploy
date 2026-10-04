# Contributing

## Conventional Commits

Subjects follow [Conventional Commits](https://www.conventionalcommits.org/).
release-please reads them on every push to `main` to populate `CHANGELOG.md`
and tag releases.

| Prefix | When |
|---|---|
| `feat:` | New role, transport profile, script, runbook, or operator capability. |
| `fix:` | Bug fix in a role, template, script, or doc. |
| `docs:` | Documentation only — no code or config change. |
| `test:` | Molecule scenarios, validators, smoke tests. |
| `refactor:` | Code restructure with no behaviour change. |
| `perf:` | Performance-only change. |
| `chore:` | Tooling and dependencies (including Renovate PRs). |
| `ci:` | CI workflow changes (`.github/workflows/*`). |
| `build:` | Build-time change (rarely applicable here). |
| `revert:` | Reverts a prior commit. |

`feat!` / `fix!` (or a `BREAKING CHANGE:` trailer) bumps the major version.

## First-time setup

The complete local-gate reference setup below targets a disposable **Ubuntu
24.04 x86-64 developer VM**, matching the hosted runner OS. Start with `mise`,
Git and Make available; run from the repository root. System packages below
follow the distribution-managed dependencies in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml); the repository does not
claim exact version pins for those packages. They include tools used by real
portable tests, not only commands checked by `check-prereqs`.

```bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y build-essential pkg-config ca-certificates curl unzip \
  coreutils util-linux jq openssl openssh-client openssh-server age restic \
  shellcheck bats ssss nginx-light cloud-init
mise trust
mise install
mise exec -- make install-hooks
```

[`mise.toml`](mise.toml) owns the exact runtime and standalone-tool pins.
`install-hooks` uses that Python to install the hash-pinned
[`requirements.txt`](requirements.txt) with `--require-hashes --no-deps`,
then installs both hooks. Python tooling does not provide PATH executables for
actionlint, shellcheck, Bats, cargo-deny, SOPS, Xray or sing-box. Continue with
the following Bash session; it reads existing pins rather than maintaining
another version list. Node uses CI's major selector, with its minimum declared
in [`tools/tasking/package.json`](tools/tasking/package.json). Run both blocks
in the same Bash session; failed installs or checksum checks stop the sequence.

```bash
set -euo pipefail
read -r setup_actionlint setup_sops setup_singbox setup_xray setup_xray_sha \
  setup_msrv setup_rust setup_node setup_providers < <(mise exec -- python - <<'PY'
from pathlib import Path
import re, tomllib, yaml
ci_text = Path('.github/workflows/ci.yml').read_text()
jobs = yaml.safe_load(ci_text)['jobs']
steps = [step for job in jobs.values() for step in job.get('steps', [])]
actionlint = next(step['env']['ACTIONLINT_VERSION'] for step in steps
                  if 'ACTIONLINT_VERSION' in step.get('env', {}))
node = next(step['with']['node-version'] for step in steps
            if 'node-version' in step.get('with', {}))
singbox = next(job['env']['SING_BOX_CLIENT_VERSION'] for job in jobs.values()
               if 'SING_BOX_CLIENT_VERSION' in job.get('env', {}))
sops = re.search(r'/sops/releases/download/v([^/]+)/sops-', ci_text).group(1)
xray = yaml.safe_load(Path('.github/actions/install-xray/action.yml').read_text())
xray_env = xray['runs']['steps'][0]['env']
msrv = re.search(r'cargo \+([0-9.]+) check', Path('Makefile').read_text()).group(1)
rust = tomllib.loads(Path('mise.toml').read_text())['tools']['rust']
print(actionlint, sops, singbox, xray_env['XRAY_VERSION'],
      xray_env['XRAY_SHA256'], msrv, rust, node,
      ','.join(jobs['terraform']['strategy']['matrix']['provider']))
PY
)
setup_gate_tools=("node@$setup_node" "aqua:rhysd/actionlint@$setup_actionlint"
  "aqua:getsops/sops@$setup_sops" "sing-box@$setup_singbox"
  "aqua:EmbarkStudios/cargo-deny@0.20.2")
```

Install those tools and initialize the local inputs used before the first gate:

```bash
set -euo pipefail
mise install "${setup_gate_tools[@]}"
mise exec -- rustup component add clippy --toolchain "$setup_rust"
mise exec -- rustup toolchain install "$setup_msrv" --profile minimal

setup_xray_dir=$(mktemp -d)
curl -fsSL --connect-timeout 10 --max-time 120 \
  "https://github.com/XTLS/Xray-core/releases/download/$setup_xray/Xray-linux-64.zip" \
  -o "$setup_xray_dir/xray.zip"
printf '%s  %s\n' "$setup_xray_sha" "$setup_xray_dir/xray.zip" | sha256sum -c -
unzip -q "$setup_xray_dir/xray.zip" -d "$setup_xray_dir"
install -d "$HOME/.local/bin"
install -m 0755 "$setup_xray_dir/xray" "$HOME/.local/bin/xray"
install -m 0644 "$setup_xray_dir/geoip.dat" "$setup_xray_dir/geosite.dat" "$HOME/.local/bin/"
rm -r "$setup_xray_dir"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export ANSIBLE_COLLECTIONS_PATH="$PWD/.ansible/collections"
mise exec "${setup_gate_tools[@]}" -- ansible-galaxy collection install \
  -r requirements.yml --collections-path "$ANSIBLE_COLLECTIONS_PATH"
mise exec "${setup_gate_tools[@]}" -- make task-tools
IFS=, read -r -a setup_provider_roots <<< "$setup_providers"
for setup_provider in "${setup_provider_roots[@]}"; do
  mise exec "${setup_gate_tools[@]}" -- terraform \
    -chdir="terraform/providers/$setup_provider" init -backend=false
done
mise exec "${setup_gate_tools[@]}" -- make check-prereqs
```

The cargo-deny version above is the binary version in the Dockerfile of the
exact `cargo-deny-action` commit selected by `ci.yml`; update it when that
action pin changes. Xray's version and Linux archive checksum come from
[the shared CI installer](.github/actions/install-xray/action.yml).
The Galaxy collections use [`requirements.yml`](requirements.yml), and
`task-tools` uses `npm ci --prefix tools/tasking --ignore-scripts` against its
lock. Provider roots come from CI's Terraform matrix; backend-disabled init
downloads their plugins without accessing remote state or provisioning. It
must precede the first `make check`: its `validate` prerequisites need installed
provider schemas before `ci-fast` reaches its own Terraform test init.
Hook installation alone does not install these dependencies.
Terraform-specific commit hooks also invoke `terraform-docs` and `tflint`:
see [`.pre-commit-config.yaml`](.pre-commit-config.yaml). Their external binary
versions are not pinned here; this `make check` recipe does not claim a complete
installer for every file hook. Prepare those tools separately before Terraform
commits; installing the hooks is not proof they have run successfully.
The commit-message hook rejects `Co-Authored-By:` trailers; Conventional
Commit subjects are not validated locally, so follow the table above.

`check-prereqs` checks command availability, the Terraform minimum and PyYAML
import; it is not the complete CI parity gate. Activate the complete tool
selection for ordinary Make commands and runbooks in this Bash
session. In a new session, repeat the pin-reading block above and this block:

```bash
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export ANSIBLE_COLLECTIONS_PATH="$PWD/.ansible/collections"
setup_tool_environment=$(mise env --shell bash "${setup_gate_tools[@]}")
eval "$setup_tool_environment"
unset setup_tool_environment
```

Run the full gate with `make check` in the activated session, or use
`mise exec "${setup_gate_tools[@]}" -- make check` explicitly. Bare
`mise exec --` recomputes the configured tool selection and can drop these
additional pins. Activation changes this session only, without editing
`mise.toml` or global defaults.
Hosted-only and live lanes remain separate in [docs/TESTING.md](docs/TESTING.md).

An ambient `python3` can otherwise miss
Ansible or use a different dependency set. Do not install `requirements.in`
as an alternative to the hash-pinned lock.

For a complete reference gate on macOS, use the Ubuntu VM above. Native Mac
checks need equivalent host tools, Darwin Xray/sing-box builds at the same
source pins, and GNU `timeout` named `timeout` on PATH. The cloud-init target
requires a native `cloud-init` or a running Docker engine for the digest-pinned
fallback image in `Makefile`. A cached Docker Xray image alone does not satisfy
the native liveness parser gate. Run native compiler-backed gates through
`build-gate`; local checks do not replace the hosted Linux/native, Molecule,
security-service or live acceptance lanes.

For credential-free development, start without provider credentials or
operator private inputs. Make reads an existing ignored `.fleet.mk` even for
local setup and test targets. If operator configuration prevents a local
check from starting, reproduce it in a clean checkout without `.fleet.mk`
before attributing it to source; preserve the operator's file. A clean shell
alone does not remove that Make include.

## Task and OpenSpec contract

Every non-trivial PR names a portfolio Task ID from `docs/tasks/issues/`.
Features, infrastructure behavior, schema, security/network, deployment
lifecycle, and cross-repository changes use an OpenSpec change; narrow waived
work records an allowed `spec_reason`. Use `./taskctl`, not direct edits to the
generated board or direct OpenSpec archive commands.

Cross-repository dependencies use qualified IDs such as
`po4yka/RIPDPI#TRN-...`. Validate them against a sibling checkout with:

```bash
make task-federation PEER_ROOT=../RIPDPI
```

## Local pre-flight

Before opening or updating a PR, in the reference setup's Bash session:

```bash
mise exec "${setup_gate_tools[@]}" -- make check
```

`make check` is the fail-closed union of `make task-check`, `make validate`, and `make ci-fast`.
It is the canonical local parity gate; `docs/TESTING.md` records the Molecule,
GitHub-native security, and credentialed deploy checks that remain separate or
CI-only. When changing a role, also run its focused
`make molecule-test ROLE=<name>` scenario when the required container runtime
is available.

## CI gates

`.github/workflows/ci.yml` owns the required PR workflow. Its `required checks`
aggregator fails unless every current required dependency succeeds.

`docs/TESTING.md` is the canonical human-readable coverage matrix, including
default Molecule roles, non-default failure scenarios, CI-only services, and
the local-versus-remote boundary. When required coverage changes, update the
workflow and that matrix together; governance tests verify their relationship.

## Adding a new role / template / script

Each artefact type has a checklist in `docs/TESTING.md`. The short
versions:

- **New role** → toggle in `group_vars/all.yml`, schema in
  `secrets/prod.secrets.example.yaml`, molecule scenario or justified
  skip in `docs/TESTING.md`.
- **New template** → variables must resolve from secrets / group_vars /
  defaults; the validators enforce this at PR time.
- **New script** → top-of-file usage block, `bash -n` clean, shellcheck
  clean, listed in the Makefile if operator-facing.

## Reviews and merge

- `CODEOWNERS` enumerates reviewers (currently single-operator).
- Branch protection requires every CI gate to pass before merge — see
  `docs/BRANCH-PROTECTION.md` for the required-status-checks list and how
  the operator applies it.
- Squash-merge is preferred for clean release-please history.

## Versioning

release-please derives the version bump from Conventional Commits subjects
(see the table above). In practice:

| Change type | Bump |
|---|---|
| New role, new vpnd subcommand, new provider, new AWG cohort | **minor** — use `feat:` |
| Bug fix in a role, template, script, or doc | **patch** — use `fix:` |
| Runbook update, knowledge-layer addition (CLAUDE.md), snapshot refresh after intentional template change | **patch** — use `docs:` or `fix:` |
| Breaking API / secrets-schema / output-schema change | **major** — use `feat!:` or add `BREAKING CHANGE:` trailer |

`CHANGELOG.md` is generated automatically; do not edit it by hand.

## Knowledge layer

If your PR touches `ansible/roles/<X>/`, `terraform/providers/<X>/`,
`scripts/`, or `vpnd/src/`, also touch the corresponding `CLAUDE.md`
(Design decisions / Done well / Pitfalls). The CI warn-gate
(`claude-md-touch.yml`) surfaces omissions but does not block merge.

Step-by-step recipes for the four most common contribution types live next
to the code they change: new role in `ansible/CLAUDE.md`, new provider in
`terraform/CLAUDE.md`, new vpnd subcommand in `vpnd/CLAUDE.md`, new AWG cohort
in `ansible/roles/amneziawg/CLAUDE.md`. Agent-facing project rules are in the
root `AGENTS.md`, which the root `CLAUDE.md` imports.

## What not to PR

- `Cloudflare CDN as filtered-path baseline` — see `docs/CDN-DECISION.md` ADR.
- A web admin panel (Marzban / Remnawave / 3x-ui) — architectural
  invariant.
- Calendar-based credential auto-rotation — rotation must be event-driven.
- Docker / K8s on the data plane — Ansible plus systemd own runtime state;
  see `docs/ARCHITECTURE.md`.
- Auto-deploy from `main` — operator-driven by design.

PRs in these directions will be closed with a pointer to the rationale.
