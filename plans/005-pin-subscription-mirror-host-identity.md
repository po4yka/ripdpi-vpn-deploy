# Plan 005: Pin the subscription mirror SSH host identity

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- ansible/roles/subscription-host/defaults/main.yml ansible/roles/subscription-host/tasks/mirror.yml ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2 ansible/roles/subscription-host/molecule/default/converge.yml ansible/roles/subscription-host/molecule/default/verify.yml secrets/schema.json secrets/prod.secrets.example.yaml tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2 tests/unit/test_subscription_mirror_host_identity.py`
> If any existing in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/001-restore-upcloud-terraform-test-baseline.md` (`8fc8536`)
- **Category**: security
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

The subscription host periodically pulls the authoritative hashed payload tree over rsync/SSH, but its shipped SSH policy uses `StrictHostKeyChecking=accept-new`. On the first connection, an active network attacker can establish the trusted key and then supply attacker-controlled client configurations. Enabled rsync mirroring must fail deployment without an operator-pinned host identity and must use only the managed known-hosts file when connecting.

## Current state

- `ansible/roles/subscription-host/defaults/main.yml:49-68` defines the opt-in mirror and currently ships trust-on-first-use:

```yaml
mirror:
  enabled: false
  backend: "rsync"
  source: ""
  rsync_opts: "-az --delete"
  ssh_key_path: "/etc/vpn-subscription/mirror_ssh_key"
  ssh_opts: "-o StrictHostKeyChecking=accept-new -o BatchMode=yes"
```

- `ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2:21-33` copies `ssh_opts` directly into the rsync remote-shell string:

```bash
SOURCE="{{ subscription.mirror.source | default('') }}"
SSH_KEY="{{ subscription.mirror.ssh_key_path | default('/etc/vpn-subscription/mirror_ssh_key') }}"
SSH_OPTS="{{ subscription.mirror.ssh_opts | default('-o StrictHostKeyChecking=accept-new -o BatchMode=yes') }}"
rsync {{ subscription.mirror.rsync_opts | default('-az --delete') }} \
  -e "ssh -i ${SSH_KEY} ${SSH_OPTS}" \
  "$SOURCE" "${DEST}/"
```

- `ansible/roles/subscription-host/tasks/mirror.yml:14-74` installs the rsync client and private key, then renders the script. It has no preflight assertion for pinned host identity and does not install a known-hosts file.
- `ansible/roles/subscription-host/molecule/default/converge.yml:19-27` enables rsync mirroring with a local source path and a stub private key. Because local rsync ignores `-e ssh`, the scenario can carry a clearly fake known-hosts line without creating an SSH server.
- `ansible/roles/subscription-host/molecule/default/verify.yml:81-145` already verifies the timer, one mirror pull, payload permissions, and private-key survival. Extend this block to verify the managed known-hosts file and fixed SSH policy, and add a fail-closed assertion for missing known-hosts content before any package or file task runs.
- `secrets/schema.json:459-475` defines the allowed `subscription.mirror` keys. `secrets/prod.secrets.example.yaml:368-388` documents the optional mirror secret/config block. Both must expose the new operator-supplied pin without including any real host key.
- `tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2` is generated from the canonical defaults by `make snapshot-update`; update it only through that command and inspect its diff.
- `scripts/template_render.py` provides `merge_render_vars()` and `render_template()` for fast template contract tests. Existing unit tests import it by adding `scripts/` to `sys.path`; follow that pattern in the new focused test.
- Repository convention: secret-bearing copy tasks use `no_log: true` and `diff: false`; credentials live outside `subscription_dir`; Ansible changes require `make validate` before commit; intentional template changes update and then check committed snapshots.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | `git diff --stat 7bdba37..HEAD -- ansible/roles/subscription-host/defaults/main.yml ansible/roles/subscription-host/tasks/mirror.yml ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2 ansible/roles/subscription-host/molecule/default/converge.yml ansible/roles/subscription-host/molecule/default/verify.yml secrets/schema.json secrets/prod.secrets.example.yaml tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2 tests/unit/test_subscription_mirror_host_identity.py` | no output |
| Focused tests | `mise exec -- python3 -m pytest tests/unit/test_subscription_mirror_host_identity.py tests/unit/test_secrets_schema.py -q` | all pass |
| Refresh generated snapshot | `mise exec -- make snapshot-update` | only the mirror script golden changes |
| Snapshot check | `mise exec -- make snapshot-check` | all templates match goldens |
| Role integration | `mise exec -- make molecule-test ROLE=subscription-host` | converge, idempotence, verify, and cleanup pass |
| Required repository gate | `mise exec -- make validate` | exit 0, or stop after recording a failure that reproduces unchanged on pristine `7bdba37` |
| Validation components if the historical gitleaks baseline blocks the aggregate gate | Run the Terraform fmt/validate loop from `Makefile`, `cd ansible && ansible-lint`, and `cd ansible && ansible-playbook playbooks/site.yml --syntax-check` | every non-gitleaks component exits 0 |
| Commit-scoped secret scan | after commit, `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |
| Diff hygiene | `git diff --check` | exit 0, no output |

## Scope

**In scope** (the only source/test files you may modify):

- `ansible/roles/subscription-host/defaults/main.yml`
- `ansible/roles/subscription-host/tasks/mirror.yml`
- `ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2`
- `ansible/roles/subscription-host/molecule/default/converge.yml`
- `ansible/roles/subscription-host/molecule/default/verify.yml`
- `secrets/schema.json`
- `secrets/prod.secrets.example.yaml`
- `tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2` (generated)
- `tests/unit/test_subscription_mirror_host_identity.py` (new)

**Out of scope** (do not modify):

- Other subscription routes, the Python serving process, nginx, issuance scripts, payload layout, mirror staging/symlink behavior, or systemd units.
- Restic mirror behavior. Restic must remain enabled without SSH known-hosts configuration.
- Private-key generation, host-key discovery, `ssh-keyscan`, or automatic trust enrollment. The operator must obtain the host public key through a trusted channel; the role must never discover and trust it at deploy/runtime.
- `ssh_opts` removal or general SSH option validation. Preserve it for additive operator transport options, but fixed trust-policy options must appear before it and must not derive from it.
- Any real hostname, private key, or host public key in fixtures, docs, snapshots, test output, or commit messages.
- `CHANGELOG.md` and unrelated snapshots or generated files.

## Git workflow

- Branch: `codex/advisor-005-pin-mirror-host-identity`
- Create one focused Conventional Commit: `fix(subscription-host): pin mirror ssh identity`.
- Do not push, merge, or open a pull request.

## Steps

### Step 1: Define the pinned host-identity inputs and fail-closed preflight

In `defaults/main.yml`, add `known_hosts: ""` and `known_hosts_path: "/etc/vpn-subscription/mirror_known_hosts"` inside `subscription.mirror`. Document that `known_hosts` contains one or more complete OpenSSH known-hosts lines obtained through a trusted channel, is mandatory only for enabled rsync mirroring, and is not populated by `ssh-keyscan`. Change the `ssh_opts` default to an empty string and describe it as additive transport customization; the template owns the non-overridable trust controls.

At the very top of `tasks/mirror.yml`, before package installation or filesystem mutation, add an `ansible.builtin.assert` preflight. It must validate the backend enumeration and require non-empty `source` plus non-empty `known_hosts` when the backend is `rsync`; retain the existing restic requirements without making known-hosts mandatory for restic. Use a concise failure message that tells the operator to pin the rsync source host identity. Do not log the contents of either the private key or known-hosts value.

Extend `secrets/schema.json` with `known_hosts` as a string and `known_hosts_path` as an absolute path under `subscription.mirror.properties`. Extend the commented example with placeholder-only known-hosts syntax and a note to obtain the real key through a trusted channel. Do not add a real or syntactically usable public key.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_secrets_schema.py -q` → all schema tests pass.

### Step 2: Install the pin and enforce it in the rsync SSH command

In `tasks/mirror.yml`, add a copy task for the operator-supplied known-hosts content when the backend is rsync. Install it at `known_hosts_path`, owned by `vpn-bootstrap:vpn-bootstrap`, mode `0600`, with `no_log: true` and `diff: false`, alongside but outside the payload tree. Notify the mirror timer only if existing credential changes already follow that pattern; otherwise preserve current handler behavior.

In `vpn-sub-mirror.sh.j2`, define `SSH_KNOWN_HOSTS` from `known_hosts_path`. Build the rsync remote-shell command with these fixed options before the additive `SSH_OPTS` value:

- `-o StrictHostKeyChecking=yes`
- `-o UserKnownHostsFile=${SSH_KNOWN_HOSTS}`
- `-o GlobalKnownHostsFile=/dev/null`
- `-o BatchMode=yes`

The rendered script must contain no `accept-new`, `StrictHostKeyChecking=no`, default user known-hosts fallback, `ssh-keyscan`, or write/update of the managed file. Keep the private-key path, rsync options, source quoting, destination, and restic branch behavior unchanged.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_subscription_mirror_host_identity.py -q` → all focused contract tests pass.

### Step 3: Add fast and Molecule regressions

Create `tests/unit/test_subscription_mirror_host_identity.py`. Render the mirror template with a synthetic enabled rsync configuration using `template_render.merge_render_vars()` and `render_template()`. Assert the result contains all four fixed SSH options, references `SSH_KNOWN_HOSTS`, retains the additive `SSH_OPTS`, and contains none of `accept-new`, `StrictHostKeyChecking=no`, or `ssh-keyscan`. Also inspect the defaults/tasks contract to prove the default is fail-closed (`known_hosts` empty), the known-hosts file is installed mode `0600`, and the preflight assertion occurs textually before the first package task. Keep assertions semantic and narrow rather than snapshotting the whole file again.

Update the Molecule converge variables with a clearly fake, non-secret known-hosts line for `worker.example.test`; keep the local mirror source so no SSH connection is attempted. In `verify.yml`, assert:

- `/etc/vpn-subscription/mirror_known_hosts` exists, is a regular file, is owned by `vpn-bootstrap`, and has mode `0600`.
- The rendered mirror script contains `StrictHostKeyChecking=yes`, the explicit `UserKnownHostsFile`, `GlobalKnownHostsFile=/dev/null`, and `BatchMode=yes`, and contains no `accept-new`.
- The existing local mirror pull and credential-survival checks still pass.
- A task-level invocation of the mirror preflight with enabled rsync and empty `known_hosts` is caught as an expected assertion failure before package/file work. Use an Ansible `block`/`rescue` or another role-local Molecule pattern; do not weaken the production assertion merely to make this test convenient.

**Verify**: `mise exec -- make molecule-test ROLE=subscription-host` → the complete scenario passes, including idempotence and the new fail-closed verification.

### Step 4: Refresh only the intended snapshot

Run `mise exec -- make snapshot-update`, then inspect `git status --short` and the generated diff. The only snapshot golden allowed to change is `tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2`; revert or stop on any unrelated generated drift. Confirm the golden has the fixed trust options and no `accept-new`.

**Verify**: `mise exec -- make snapshot-check` → all templates match their committed goldens.

### Step 5: Run the required repository gate and commit

Run the full `mise exec -- make validate` gate because this change touches Ansible. If it fails, compare the failure with pristine `7bdba37`; do not skip or suppress gitleaks. The confirmed 2026-07-11 baseline has two historical gitleaks findings in out-of-scope test files, so if and only if the aggregate gate fails solely on those unchanged findings, run the Terraform fmt/validate loop, `ansible-lint`, and site syntax check individually and require them all to pass. Run `git diff --check`, inspect the entire diff, and confirm the exact scope. Commit normally with hooks enabled using `fix(subscription-host): pin mirror ssh identity`, then run `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` to prove the new commit adds no leak. Never use `--no-verify`, a skip variable, an allowlist change, or a gitleaks disable flag.

**Verify**: after commit, `git status --short` has no output and `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the nine in-scope files.

## Test plan

- Fast unit coverage proves the generated command is strict, does not retain trust-on-first-use, and is wired to the managed file.
- Schema coverage proves the example remains valid and the new keys are allowed without relaxing unknown-property rejection.
- Molecule proves enabled rsync deployments install the pinned file with the intended ownership/mode, valid local mirroring remains operational and idempotent, and omitted pin content fails before side effects.
- Snapshot coverage makes the default rendered trust policy reviewable and prevents silent regression.
- `make validate` supplies repository-wide Ansible syntax/lint, formatting, and secret-scanning gates.

## Done criteria

- [ ] Enabled rsync mirroring fails before package/file changes when `known_hosts` is empty or omitted.
- [ ] Restic mirroring does not require SSH known-hosts configuration.
- [ ] The role installs the operator-provided known-hosts content outside `subscription_dir` as `vpn-bootstrap:vpn-bootstrap` mode `0600`.
- [ ] The rendered rsync transport uses `StrictHostKeyChecking=yes`, the explicit managed `UserKnownHostsFile`, `GlobalKnownHostsFile=/dev/null`, and `BatchMode=yes` before additive `ssh_opts`.
- [ ] No in-scope source, fixture, or golden contains `accept-new`, `StrictHostKeyChecking=no`, or `ssh-keyscan` for the mirror path.
- [ ] `mise exec -- python3 -m pytest tests/unit/test_subscription_mirror_host_identity.py tests/unit/test_secrets_schema.py -q` passes.
- [ ] `mise exec -- make snapshot-check` passes.
- [ ] `mise exec -- make molecule-test ROLE=subscription-host` passes including idempotence.
- [ ] `mise exec -- make validate` passes, or its only failure is the two unchanged historical findings that reproduce on pristine `7bdba37`; in that baseline case every non-gitleaks component passes individually and `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` passes after the normal hooked commit.
- [ ] `git diff --check` passes; exactly the nine in-scope files are committed; the worktree is clean; the executor reports the commit SHA.

## STOP conditions

Stop and report instead of improvising if:

- Any existing in-scope file drifted from `7bdba37` or no longer matches the excerpts.
- A checked-in production configuration relies on `accept-new` or lacks a trustworthy migration path for the required host pin.
- Enforcing a dedicated known-hosts file requires host-key discovery, external network access, or storing any real key material in the repository.
- Fixed trust controls cannot be made authoritative while preserving additive `ssh_opts` without changing rsync invocation architecture; report the conflict instead of silently allowing overrides.
- The Molecule scenario cannot exercise the fail-closed assertion without touching out-of-scope files or weakening production behavior.
- Snapshot update changes any golden other than the mirror script.
- A verification gate fails twice after a reasonable in-scope correction, except the documented historical gitleaks baseline above; any new or changed gitleaks finding remains a STOP.
- The implementation requires modifying any file outside the nine-file scope.

## Maintenance notes

Host-key rotation is deliberately operator-controlled: add the replacement key through a trusted channel, deploy the managed file, then remove the old key after the transition. Never replace this with `ssh-keyscan`, `accept-new`, or a writable default known-hosts file. Review future `ssh_opts` changes to ensure fixed command-line trust options remain first and continue to isolate the connection from global host-key databases.
