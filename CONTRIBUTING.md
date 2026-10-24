# Contributing

Thank you for helping. This page covers the development setup, the pull
request flow and where the detailed rules live. The project rules that
every contributor and coding agent follows are in [AGENTS.md](AGENTS.md);
the documentation rules are in [docs/STYLE.md](docs/STYLE.md). Please read
[the code of conduct](CODE_OF_CONDUCT.md) and
[the security policy](.github/SECURITY.md) first.

## What to work on

- Open tasks live in `docs/tasks/issues/`; `make task-list` prints them and
  [docs/tasks/README.md](docs/tasks/README.md) explains the lifecycle. Every
  non-trivial PR names a Task ID.
- Features, infrastructure behaviour, schemas, security or network changes,
  deployment lifecycle and cross-repository contracts go through an
  OpenSpec change. Narrow work records an allowed `spec_reason`. Use
  `./taskctl`; never edit the generated board or run archive commands
  directly.
- Pull requests in these directions are closed with a pointer to the
  rationale: a CDN as the filtered-path baseline
  ([decision 0001](docs/decisions/0001-cdn-not-filtered-path-baseline.md)),
  a web admin panel, calendar-based credential rotation, Docker or
  Kubernetes on the data plane (Ansible plus systemd own runtime state),
  auto-deploy from `main`
  ([architecture rationale](docs/explanation/architecture-rationale.md)).

## First-time setup

The complete local-gate reference setup targets a disposable **Ubuntu
24.04 x86-64 developer VM**, matching the hosted runner OS. Start with
`mise`, Git and Make available and run from the repository root. System
packages follow the distribution-managed dependencies in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml); the repository does
not pin their versions.

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

[`mise.toml`](mise.toml) owns the runtime and standalone-tool pins.
`install-hooks` uses that Python to install the hash-pinned
[`requirements.txt`](requirements.txt) with `--require-hashes --no-deps`,
then installs the pre-commit and commit-message hooks. Python tooling does
not provide actionlint, shellcheck, Bats, SOPS, Xray or sing-box. The next
block reads their pins from CI instead of maintaining a second list; run
both blocks in the same Bash session.

```bash
set -euo pipefail
read -r setup_actionlint setup_sops setup_singbox setup_xray setup_xray_sha \
  setup_node setup_providers < <(mise exec -- python - <<'PY'
from pathlib import Path
import re, yaml
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
print(actionlint, sops, singbox, xray_env['XRAY_VERSION'],
      xray_env['XRAY_SHA256'], node,
      ','.join(jobs['terraform']['strategy']['matrix']['provider']))
PY
)
setup_gate_tools=("node@$setup_node" "aqua:rhysd/actionlint@$setup_actionlint"
  "aqua:getsops/sops@$setup_sops" "sing-box@$setup_singbox")
```

Install those tools and initialise the local inputs used before the first
gate:

```bash
set -euo pipefail
mise install "${setup_gate_tools[@]}"
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
export PATH="$HOME/.local/bin:$PATH"
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

Notes on that block:

- Xray's version and Linux archive checksum come from
  [the shared CI installer](.github/actions/install-xray/action.yml). On a
  macOS workstation install the matching `Xray-macos-arm64-v8a.zip` or
  `Xray-macos-64.zip` asset of the same release, verified against its
  `.dgst` file; the templates-render commit hook needs the binary on `PATH`.
- Backend-disabled Terraform init downloads provider plugins without
  touching remote state. It must precede the first `make check`.
- Terraform-specific commit hooks also invoke `terraform-docs` and
  `tflint` (see [`.pre-commit-config.yaml`](.pre-commit-config.yaml)); their
  versions are not pinned here.
- `check-prereqs` checks command availability only; it is not the CI
  parity gate.

In a new shell, repeat the pin-reading block and activate the tools:

```bash
export PATH="$HOME/.local/bin:$PATH"
export ANSIBLE_COLLECTIONS_PATH="$PWD/.ansible/collections"
setup_tool_environment=$(mise env --shell bash "${setup_gate_tools[@]}")
eval "$setup_tool_environment"
unset setup_tool_environment
```

Bare `mise exec --` recomputes the configured tool selection and can drop
these additional pins, so run the gate as
`mise exec "${setup_gate_tools[@]}" -- make check` or in the activated
session. An ambient `python3` can miss Ansible or use a different
dependency set; do not install `requirements.in` as an alternative to the
hash-pinned lock.

For a complete reference gate on macOS use the Ubuntu VM. Native Mac
checks need equivalent host tools, Darwin Xray and sing-box builds at the
same pins, GNU `timeout` named `timeout` and a real `flock` on `PATH`. The
cloud-init target needs a native `cloud-init` or a running Docker engine
for the digest-pinned fallback image. Compiler-backed native gates run
through `build-gate`; local checks do not replace the hosted Linux, Molecule,
security-service or live acceptance lanes.

Make reads an existing ignored `.fleet.mk` even for local test targets. If
operator configuration prevents a local check from starting, reproduce it
in a clean checkout without `.fleet.mk` before attributing it to source.

## Pull request flow

1. Branch from `main`. Keep diffs focused; a bug fix does not carry
   surrounding cleanup.
2. Run the narrowest check that exercises the change, then the full gate:

   ```bash
   mise exec "${setup_gate_tools[@]}" -- make check
   ```

   `make check` is the fail-closed union of `make task-check`,
   `make validate` and `make ci-fast`, whose unit tests include the docs guards. When changing a
   role, also run `make molecule-test ROLE=<name>` when Docker is available.
   [The testing reference](docs/reference/testing.md) maps each area to its
   CI coverage and names the lanes that remain CI-only.
3. Fill in [the pull request template](.github/PULL_REQUEST_TEMPLATE.md):
   Task ID, scope, the exact commands you ran and what they showed. A
   skipped or failing check is reported as such.
4. `.github/workflows/ci.yml` owns the required PR workflow. Its
   `required checks` aggregator requires every selected job to succeed and
   every unselected job to be planned as skipped.
   [Branch protection](docs/how-to/branch-protection.md) lists the required
   statuses. Squash-merge is preferred; task lifecycle PRs that contain a
   terminal record followed by archival keep their separate commits through
   the allowed linear rebase merge.

## Commit messages

Subjects follow [Conventional Commits](https://www.conventionalcommits.org/).
release-please reads them on every push to `main` to maintain
`CHANGELOG.md` and tag releases, so `CHANGELOG.md` is never edited by hand.

| Prefix | When | Bump |
|---|---|---|
| `feat:` | New role, transport profile, provider, vpnd subcommand, AWG cohort or operator capability | minor |
| `fix:` | Bug fix in a role, template, script or document | patch |
| `docs:` | Documentation only | patch |
| `test:` | Molecule scenarios, validators, smoke tests | patch |
| `refactor:` / `perf:` | Restructure or performance change without behaviour change | patch |
| `chore:` / `build:` / `ci:` | Tooling, dependencies (including Renovate PRs), workflows | none (hidden section) |
| `revert:` | Reverts a prior commit | as reverted |

`feat!:`, `fix!:` or a `BREAKING CHANGE:` trailer bumps the major version. Every
type with a visible section in `.github/release-please-config.json` produces a
release, so a `docs:` commit alone on `main` creates a patch release PR.
Do not add `Co-Authored-By:` trailers; the commit-message hook rejects them.

## Adding a role, template or script

- **New Ansible role:** follow the recipe in [`ansible/CLAUDE.md`](ansible/CLAUDE.md).
  In short: write the role under `ansible/roles/<name>/`, reference it in
  `ansible/playbooks/site.yml` behind a `vpn.enable_<name>` toggle, add the
  toggle to `ansible/group_vars/all.yml` and every profile, classify it in
  `ansible/role-tiers.yml`, add any new secret keys to
  `secrets/prod.secrets.example.yaml` (the coverage validator fails PRs
  that miss this), add a Molecule scenario and the CI matrix entry or a
  justified skip in the coverage matrix, give the role a `CLAUDE.md` with
  an `AGENTS.md -> CLAUDE.md` symlink, and update the governance counts.
- **New template:** reference only variables that exist in role defaults,
  group_vars or the secrets schema. `*.json.j2` renders are validated as
  JSON; nginx `*.conf.j2` templates under a role whose directory name
  contains `nginx` run through `nginx -t`. Refresh golden snapshots with
  `make snapshot-update` after an intentional change.
- **New script:** `bash -n` and `shellcheck -s bash -S warning` must pass;
  add `# shellcheck disable=SCXXXX  # reason` for justified exceptions.
  Include a top-of-file comment block describing usage, environment and
  exit codes, and list the script in the Makefile if it is operator-facing.
  Conventions are in [the bash-scripting skill](.agents/skills/bash-scripting/SKILL.md).
- **New Terraform provider:** [`terraform/CLAUDE.md`](terraform/CLAUDE.md).
- **New vpnd subcommand:** [`vpnd/CLAUDE.md`](vpnd/CLAUDE.md).
- **New AmneziaWG cohort:** [`ansible/roles/amneziawg/CLAUDE.md`](ansible/roles/amneziawg/CLAUDE.md).

## Documentation

- The tree, status line, naming and templates are defined in
  [docs/STYLE.md](docs/STYLE.md); [docs/README.md](docs/README.md) must list
  every page. `make docs-check` runs the guards.
- `docs/reference/make-targets.md`, `docs/reference/vpnd-commands.md` and
  `docs/llms.txt` are generated: run `make docs-reference` after changing
  the Makefile help text, the vpnd command tree or any page.
- If your PR touches `ansible/roles/<X>/`, `terraform/providers/<X>/`,
  `scripts/`, `tests/` or `vpnd/src/`, also update the folder's `CLAUDE.md`
  (Design decisions / What's done well / Pitfalls). A CI warn-gate
  surfaces omissions.
- Cross-repository references use qualified IDs such as
  `po4yka/RIPDPI#TRN-...`; validate them with
  `make task-federation PEER_ROOT=../RIPDPI`.
