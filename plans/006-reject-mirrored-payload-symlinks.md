# Plan 006: Reject symlinks and non-regular subscription payload state

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 9447d22..HEAD -- ansible/roles/subscription-host/CLAUDE.md ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2 ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2 ansible/roles/subscription-host/molecule/default/converge.yml ansible/roles/subscription-host/molecule/default/verify.yml tests/unit/test_vpn_bootstrap.py tests/unit/test_subscription_mirror_host_identity.py tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2 tests/snapshot/golden/subscription-host/templates/vpn-bootstrap.py.j2`
> If any existing in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/001-restore-upcloud-terraform-test-baseline.md` (`8fc8536`) and `plans/005-pin-subscription-mirror-host-identity.md` (`75c7d55`)
- **Category**: security
- **Planned at**: integration commit `9447d22`, 2026-07-11 (Plan 005 plus Plan 001's validation baseline)

## Why this matters

The rsync mirror uses archive mode, which preserves source symlinks, and the subscription server reads hashed payload paths with `Path.read_bytes()`, which follows symlinks. A compromised mirror source can therefore place a correctly named symlink to a local file readable by `vpn-bootstrap`; a bearer-token request can receive that local file. The fix must reject unsafe filesystem entries at ingest and independently refuse to follow them at request time so there is no exploitable validation race.

## Current state

- `ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2:32-34` invokes configurable archive-mode rsync directly into the live tree:

```bash
rsync {{ subscription.mirror.rsync_opts | default('-az --delete') }} \
  -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${SSH_KNOWN_HOSTS} -o GlobalKnownHostsFile=/dev/null -o BatchMode=yes ${SSH_OPTS}" \
  "$SOURCE" "${DEST}/"
```

- `vpn-sub-mirror.sh.j2:50-54` also restores restic snapshots directly into `DEST`, so validation must apply to both backends rather than relying only on rsync flags.
- `vpn-sub-mirror.sh.j2:64-71` currently performs recursive ownership/permission repair without first rejecting symlinks, nested directories, special files, or unexpected names.
- `ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2:106-115` checks metadata with `is_file()` and `read_text()`, both of which follow symlinks. Lines 154-175 derive a 64-hex hashed payload path and call `path.read_bytes()`, which also follows symlinks.
- `_is_revoked()` at `vpn-bootstrap.py.j2:63-81` reads the revocation file with normal `Path.open()`. Reuse the same safe regular-file reader there so every security-relevant read has one contract.
- `tests/unit/test_vpn_bootstrap.py` renders and starts the service against temporary paths, exposes `service.sub_dir`, and already asserts 503 plus explicit audit outcomes for corrupt state. Extend this exact harness with real symlinks and a FIFO; do not mock `Path.is_file()`.
- `tests/unit/test_subscription_mirror_host_identity.py` renders the mirror shell template and asserts fixed security options. Extend it to lock fixed rsync type exclusions and the post-transfer validation contract.
- The Molecule source fixture currently contains one valid 64-hex payload and `.meta` sidecar. Add a malicious symlink with another valid hash-shaped filename and prove it never lands in the live tree.
- Both changed templates have committed generated goldens. Refresh only those two files through `make snapshot-update`.
- The role-local `CLAUDE.md` uses the required three-section format and must record the new no-follow/regular-file invariant without hard-wrapping new prose.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Focused service and mirror tests | `mise exec -- python3 -m pytest tests/unit/test_vpn_bootstrap.py tests/unit/test_subscription_mirror_host_identity.py -q` | all pass |
| Refresh generated snapshots | `mise exec -- make snapshot-update` | only the two in-scope subscription-host goldens change |
| Snapshot check | `mise exec -- make snapshot-check` | all templates match goldens |
| Rendered shell syntax | `bash -n tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2` | exit 0 |
| Rendered shell lint | `shellcheck -s bash -S warning tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2` | exit 0, no warnings |
| Role integration | `DOCKER_HOST=unix:///Users/po4yka/.docker/run/docker.sock mise exec -- make molecule-test ROLE=subscription-host` | syntax, converge, idempotence, verify, and destroy pass |
| Required aggregate gate | `mise exec -- make validate` | reaches only the documented historical gitleaks baseline; no new failure |
| Non-gitleaks validation | exact Terraform fmt/validate loop from `Makefile`, then `cd ansible && ansible-lint && ansible-playbook playbooks/site.yml --syntax-check` | all pass |
| Commit-scoped secret scan | after commit, `mise exec -- gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | no leaks in the new commit |
| Diff hygiene | `git diff --check` | exit 0, no output |

## Scope

**In scope** (the only source/test files you may modify):

- `ansible/roles/subscription-host/CLAUDE.md`
- `ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2`
- `ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2`
- `ansible/roles/subscription-host/molecule/default/converge.yml`
- `ansible/roles/subscription-host/molecule/default/verify.yml`
- `tests/unit/test_vpn_bootstrap.py`
- `tests/unit/test_subscription_mirror_host_identity.py`
- `tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2` (generated)
- `tests/snapshot/golden/subscription-host/templates/vpn-bootstrap.py.j2` (generated)

**Out of scope** (do not modify):

- Mirror credentials, SSH pinning, systemd identities, secret schema/example, role tasks/defaults, issuance scripts, nginx, token formats, or audit-record keys.
- A full staging/generation/promotion redesign. The no-follow serving boundary is the race-free security control; this plan adds ingest rejection without changing payload-directory ownership or route layout.
- Restic repository semantics, snapshot selection, or retention.
- Automatic deletion of unsafe entries. Fail the mirror run and leave evidence for the operator; never follow, chmod, chown, or serve the entry.
- Changes to valid payload response bodies, single-use consumption, expiry semantics, revocation semantics, or existing audit outcomes.
- Any real secret, private key, host key, token, or externally sourced credential in tests/docs/commits.
- Any snapshot outside the two named generated goldens.

## Git workflow

- Branch: `codex/advisor-006-reject-mirror-symlinks`
- Create one focused Conventional Commit: `fix(subscription-host): reject unsafe mirrored payloads`.
- Do not push, merge, or open a pull request.

## Steps

### Step 1: Make subscription state reads no-follow and regular-file-only

In `vpn-bootstrap.py.j2`, import the stdlib modules needed for descriptor-level file validation (`stat` and, if used for diagnostics, `errno`). Add one small helper that opens a path with `os.open` using `O_RDONLY | O_NOFOLLOW | O_NONBLOCK` plus `O_CLOEXEC` when available, immediately checks `os.fstat(fd).st_mode` with `stat.S_ISREG`, and only then reads bytes from that descriptor. It must close the descriptor on every path. A missing path must remain distinguishable from an unsafe/unreadable path.

Use the helper for payload bytes, metadata bytes, and revocation-state bytes. Preserve these observable contracts:

- Missing payload: 410 with audit outcome `unknown`.
- Symlink, FIFO, directory, device, permission error, or other unsafe payload state: 503 with audit outcome `payload-unavailable`; never include filesystem paths or file contents in the HTTP response.
- Missing/unreadable/unsafe revocation state: existing 503 with `revocation-unavailable`.
- Missing metadata: no expiry; unreadable/unsafe/malformed metadata: existing 503 with `expiry-unavailable`.
- Valid regular files retain current response, expiry, revocation, and single-use behavior.

Do not use `Path.resolve()`, `is_file()`, `lstat()` followed by a separate normal open, or any other check-then-open sequence. The descriptor opened with `O_NOFOLLOW` and validated with `fstat` is the security boundary. `O_NONBLOCK` is required so a FIFO cannot hang a request before type validation.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_vpn_bootstrap.py -q` → all existing and new service tests pass.

### Step 2: Reject unsafe mirror entry types and names

In the rsync branch of `vpn-sub-mirror.sh.j2`, append fixed `--no-links --no-devices --no-specials` options after the configurable `rsync_opts` value so archive mode or earlier additive options cannot preserve unsafe entry types. Keep all Plan 005 SSH identity options unchanged.

After either rsync or restic completes and before any recursive `chown`, `chmod`, or successful exit, validate `DEST/sub` and `DEST/bootstrap`:

- Both route directories must exist as real directories, not symlinks.
- They may contain only direct child regular files; no nested directory or other entry type is allowed.
- Filenames must be exactly 64 lowercase hexadecimal characters, optionally followed by `.meta`.
- Iterate safely with NUL delimiters so newline-bearing attacker-controlled names cannot corrupt validation or diagnostics.
- On the first violation, print a concise `vpn-sub-mirror: unsafe payload entry` diagnostic to stderr and exit nonzero. Do not print file contents, follow the entry, or run recursive ownership/permission changes.

The validator must run for both backends. It may identify the offending path in stderr because payload filenames are hashes, but it must not dereference it. Do not automatically delete unsafe entries.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_subscription_mirror_host_identity.py -q && bash -n tests/snapshot/golden/subscription-host/templates/vpn-sub-mirror.sh.j2` after snapshot refresh → focused contract tests pass and the rendered script parses.

### Step 3: Add exploit-shaped regressions

Extend `tests/unit/test_vpn_bootstrap.py` with these real-filesystem cases:

1. A valid hash-named payload symlink pointing to a temporary local file containing a sentinel secret. A GET returns 503, audit outcome is `payload-unavailable`, and neither body nor audit record contains the sentinel.
2. A valid regular payload whose `.meta` path is a symlink to a local file. A GET returns 503 and audits `expiry-unavailable`.
3. A FIFO at a valid payload path. The request returns 503 promptly and audits `payload-unavailable`; it must not hang until the HTTP client timeout.
4. A symlinked revocation file. A GET returns 503 and audits `revocation-unavailable`.

Extend `tests/unit/test_subscription_mirror_host_identity.py` to assert the rendered rsync command places `--no-links`, `--no-devices`, and `--no-specials` after configurable rsync options, and that the shared post-transfer validator checks both route directories, uses NUL-safe iteration, enforces the hash/`.meta` filename pattern, and runs before recursive permission repair.

In Molecule converge, seed the mirror source with a symlink whose basename is a different valid 64-hex hash and whose target is the mirror private-key path. In verify, assert the normal payload still lands, the malicious hash path does not exist in the live route, the revocation file still exists after the pull, and the rendered script contains all fixed type exclusions. Preserve the Plan 005 known-host identity and missing-pin checks.

**Verify**: run the focused pytest command and the full Molecule command from the command table → all pass; Molecule idempotence reports zero changes.

### Step 4: Refresh documentation and exactly two generated snapshots

Update the role `CLAUDE.md` three-section knowledge layer with the durable invariant: mirror inputs are untrusted filesystem state; only hash-shaped regular files are accepted; the server uses descriptor-level no-follow reads as the final boundary. Keep each section under approximately 40 lines and do not hard-wrap new paragraphs.

Run `mise exec -- make snapshot-update`. Inspect `git status --short`; exactly the mirror shell golden and bootstrap Python golden may change. Confirm both reflect only their source templates, then run snapshot check, Bash syntax, and ShellCheck from the command table.

**Verify**: snapshot check, Bash syntax, and ShellCheck all exit 0.

### Step 5: Run validation and commit normally

Run `mise exec -- make validate` before committing. The integration base includes Plan 001, so Terraform fmt/validate must pass; the aggregate gate is expected to stop only at the two unchanged historical gitleaks findings already present on pristine `7bdba37`. Do not suppress or allowlist them. Run every non-gitleaks component individually and require success. Run `git diff --check`, inspect the full diff, and confirm exactly the nine in-scope files.

Commit normally with hooks enabled using `fix(subscription-host): reject unsafe mirrored payloads`. Never use `--no-verify` or a skip variable. After commit, run the scoped gitleaks command and confirm the worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the nine in-scope files and `git status --short` has no output.

## Test plan

- Use real symlinks and a real FIFO in the existing HTTP fixture; the regression must exercise the same kernel path resolution as production.
- Assert both the HTTP status/audit outcome and absence of sentinel data, so a test cannot pass merely because the handler crashed.
- Keep valid regular payload/meta tests unchanged to prove compatibility.
- Render the actual mirror template for command-order and validation assertions rather than checking source fragments alone.
- Molecule proves the rsync backend skips a malicious source symlink while still mirroring valid payloads, retaining revocation state, and remaining idempotent.
- Snapshot diffs are review surfaces, not substitutes for behavior assertions.

## Done criteria

- [ ] Payload, metadata, and revocation reads use one descriptor-level `O_NOFOLLOW` plus `fstat(S_ISREG)` helper; no security decision uses check-then-open.
- [ ] Symlinked or non-regular payload state returns 503 without leaking target contents; missing payload remains 410.
- [ ] Rsync fixed options reject links, devices, and special files after configurable options.
- [ ] Both mirror backends validate real route directories, direct-child regular files, and exact hash/`.meta` names before permission repair.
- [ ] Unit regressions cover payload symlink, metadata symlink, FIFO, and revocation symlink with meaningful status/audit/non-leak assertions.
- [ ] Molecule proves the malicious source symlink is not installed, the valid payload is installed, revocation state survives, and idempotence passes.
- [ ] Focused pytest, snapshot check, rendered Bash syntax/ShellCheck, and full subscription-host Molecule all pass.
- [ ] `make validate` is run; its only aggregate failure is the documented historical gitleaks baseline; Terraform fmt/validate, ansible-lint, and site syntax pass individually.
- [ ] The new commit's scoped gitleaks scan passes without skips or allowlist changes.
- [ ] Exactly nine in-scope files are committed; the worktree is clean; the executor reports the commit SHA.

## STOP conditions

Stop and report instead of improvising if:

- Any existing in-scope file drifted from integration commit `9447d22`.
- Valid issued payloads use nested directories, uppercase hashes, alternate sidecar suffixes, symlinks, hard links that must be preserved, or other shapes outside the specified allowlist.
- The target Python/runtime lacks `O_NOFOLLOW` or cannot safely open FIFOs nonblocking.
- Restic requires a different restored directory layout that cannot be validated without changing its documented semantics.
- The rsync version in the Molecule image does not support the fixed negative type options.
- Snapshot update changes any golden outside the two named files.
- Any new gitleaks finding appears, any non-gitleaks validation component fails, or normal commit hooks fail.
- A verification gate fails twice after a reasonable in-scope correction.
- The implementation requires modifying a tenth file or any out-of-scope behavior.

## Maintenance notes

The serving process's descriptor-level no-follow reader is the final security boundary and must remain even if mirror staging is redesigned later. Mirror validation is defense in depth and an operational diagnostic; it is not sufficient alone because sync/restore writes directly into the live tree. Any future payload sidecar or directory shape must update the allowlist, unit tests, Molecule fixture, and both source/snapshot templates together.
