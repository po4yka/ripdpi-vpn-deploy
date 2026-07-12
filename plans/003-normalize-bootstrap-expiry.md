# Plan 003: Normalize bootstrap expiry before publishing payload metadata

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` — unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- scripts/issue-bootstrap.sh tests/unit/test_subscription_expiry.py`
> If either in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`issue-bootstrap.sh --expires` currently accepts arbitrary text, uploads the subscription payload, and then manually interpolates that text into JSON metadata. Malformed timestamps therefore create a URL that appears successfully issued but fails closed with HTTP 503 when the server reads its sidecar; quote or control characters can also make the metadata invalid JSON. The long-lived subscription issuer already has the correct behavior: normalize dates and RFC 3339 timestamps before any Terraform or remote action, then serialize metadata with `jq --arg`. The bootstrap issuer should use that same contract.

## Current state

- `scripts/issue-bootstrap.sh` issues one-time `/bootstrap/<token>` payloads. It parses `--expires` at lines 30–38, contacts Terraform at lines 45–47, uploads the payload at lines 77–78, and only then constructs metadata with shell string interpolation at lines 80–84.
- `scripts/issue-sub-token.sh:46-53` is the repository exemplar: it calculates `REPO_ROOT`, normalizes non-empty expiry through `scripts/normalize-subscription-expiry.py`, and does so before Terraform or remote calls.
- `scripts/issue-sub-token.sh:86-89` serializes expiry and client metadata with `jq -nc --arg`, preventing quote/control-character corruption.
- `scripts/normalize-subscription-expiry.py` accepts `YYYY-MM-DD` and RFC 3339 timestamps with an explicit offset, emits canonical UTC with `Z`, and rejects everything else.
- `tests/unit/test_subscription_expiry.py` already tests the normalizer and the long-lived issuer with hermetic PATH stubs. Extend this file rather than creating a parallel harness.
- Shell scripts use `set -euo pipefail`, quote operator input, and fail before external mutation when validation is invalid; preserve these conventions from `scripts/CLAUDE.md`.

Current excerpts:

```bash
# scripts/issue-bootstrap.sh:40-47
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
SUBSCRIPTION_DIR="${SUBSCRIPTION_DIR:-/var/lib/vpn-subscription}"

server_ip="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
```

```bash
# scripts/issue-bootstrap.sh:80-85
if [[ -n "$EXPIRES" ]]; then
  meta="{\"expires\":\"${EXPIRES}\"}"
  printf '%s' "$meta" | ssh "${admin_user}@${server_ip}" \
    "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}.meta'"
fi
```

```bash
# scripts/issue-sub-token.sh:46-53,86-89
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$FORMAT" in
  singbox|ripdpi) ;;
  *) echo "format must be singbox or ripdpi" >&2; exit 1 ;;
esac
if [[ -n "$EXPIRES" ]]; then
  EXPIRES="$(python3 "${REPO_ROOT}/scripts/normalize-subscription-expiry.py" "$EXPIRES")"
fi

if [[ -n "$EXPIRES" ]]; then
  meta="$(jq -nc --arg expires "$EXPIRES" --arg client "$CLIENT" '{expires: $expires, client: $client}')"
```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | `git diff --stat 7bdba37..HEAD -- scripts/issue-bootstrap.sh tests/unit/test_subscription_expiry.py` | no output |
| Shell syntax | `bash -n scripts/issue-bootstrap.sh` | exit 0 |
| Shell lint | `shellcheck -s bash -S warning scripts/issue-bootstrap.sh` | exit 0, no findings |
| Focused expiry tests | `mise exec -- python3 -m pytest tests/unit/test_subscription_expiry.py -q` | all tests pass |
| Audit-hook regression | `mise exec -- python3 -m pytest tests/unit/test_audit_log_hooks.py -q` | all tests pass |
| Diff check | `git diff --check` | exit 0 |
| Worktree check | `git status --short` | only the two in-scope files before commit; clean after commit |

## Scope

**In scope** (the only files you should modify):

- `scripts/issue-bootstrap.sh`
- `tests/unit/test_subscription_expiry.py`

**Out of scope** (do not touch):

- `scripts/issue-sub-token.sh` and `scripts/normalize-subscription-expiry.py`; they are the accepted implementation and should be reused unchanged.
- Subscription-host nginx/Python service, schema, role tasks, templates, and Molecule scenarios.
- Payload generation, token generation, hashing, SSH destination paths, QR behavior, audit-log format, or Makefile wrappers.
- Documentation and `scripts/CLAUDE.md`; this change brings the bootstrap issuer into the already-documented expiry contract without changing architecture.
- Dependencies, requirements, and lockfiles.

## Git workflow

- Branch: `codex/advisor-003-bootstrap-expiry`
- Make one focused Conventional Commit after all gates pass: `fix(subscription): validate bootstrap expiry`
- Stage only the two in-scope files.
- Do not push, merge, or open a PR.

## Steps

### Step 1: Normalize expiry before any external operation

In `scripts/issue-bootstrap.sh`, immediately after `REPO_ROOT` is calculated and before `PROVIDER`, Terraform output, token generation, payload emission, SOPS, or SSH calls, normalize non-empty `EXPIRES` exactly as `issue-sub-token.sh` does:

```bash
if [[ -n "$EXPIRES" ]]; then
  EXPIRES="$(python3 "${REPO_ROOT}/scripts/normalize-subscription-expiry.py" "$EXPIRES")"
fi
```

Do not catch or downgrade a normalizer failure; `set -e` must stop issuance. Keep empty expiry as the no-sidecar path.

**Verify**: `bash -n scripts/issue-bootstrap.sh` and `shellcheck -s bash -S warning scripts/issue-bootstrap.sh` → both exit 0.

### Step 2: Serialize metadata with `jq`

Replace the manually interpolated JSON string with the same safe construction used by `issue-sub-token.sh`:

```bash
meta="$(jq -nc --arg expires "$EXPIRES" --arg client "$CLIENT" '{expires: $expires, client: $client}')"
```

Preserve the existing 0600 remote install path and only create the sidecar when expiry is non-empty. The normalized expiry printed to the operator and written to the audit note should remain the same `EXPIRES` value, so every surface reports one canonical instant.

**Verify**: `bash -n scripts/issue-bootstrap.sh` and `shellcheck -s bash -S warning scripts/issue-bootstrap.sh` → both exit 0.

### Step 3: Extend the existing hermetic issuer tests

In `tests/unit/test_subscription_expiry.py`:

1. Add a constant for `scripts/issue-bootstrap.sh` beside `ISSUER`.
2. Reuse `_issuer_env` for bootstrap tests; do not add real network, Terraform, SOPS, or secrets dependencies.
3. Add a successful bootstrap issuance test using an offset timestamp such as `2027-01-01T03:59:59+04:00`. Assert:
   - exit code is 0;
   - payload and metadata files were written by the SSH stub;
   - metadata parses as JSON;
   - `meta["expires"]` is the canonical `2026-12-31T23:59:59Z`;
   - `meta["client"]` equals the requested client;
   - operator output uses the canonical value, not the raw offset form.
4. Add or parameterize a date-only bootstrap case to prove `2027-01-01` becomes `2027-01-01T00:00:00Z`.
5. Extend the invalid-expiry-before-mutation test to cover both issuer scripts. Include ordinary invalid text and a quote-bearing/JSON-breaking value. The marker stubs for Terraform and SSH must remain untouched, proving validation happens before external actions.

If bootstrap execution exposes a missing hermetic command, add only the narrow PATH stub required inside this existing test file. Do not alter production code to accommodate tests.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_subscription_expiry.py -q` → all tests pass.

### Step 4: Run regressions and commit

Run the audit-hook regression because `issue-bootstrap.sh` must retain its post-success audit call. Review the full diff and `git diff --check`, stage only the two in-scope files, and commit.

**Verify**:

- `mise exec -- python3 -m pytest tests/unit/test_audit_log_hooks.py -q` → all tests pass.
- `bash -n scripts/issue-bootstrap.sh` → exit 0.
- `shellcheck -s bash -S warning scripts/issue-bootstrap.sh` → exit 0.
- `git diff --check` → exit 0.
- `git show --stat --oneline HEAD` lists only the two in-scope files.
- `git status --short` is empty after commit.

## Test plan

- Preserve all existing normalizer and long-lived issuer tests.
- Add successful bootstrap cases for date-only and offset RFC 3339 input.
- Assert metadata is valid JSON and carries canonical UTC plus client identity.
- Assert operator output reports the canonical instant.
- Parameterize invalid-input tests over both issuers and include a JSON-breaking string.
- Prove invalid expiry triggers neither Terraform nor SSH.
- Retain the structural audit-hook test for the bootstrap issuer.

## Done criteria

- [ ] Bootstrap expiry is normalized before Terraform, payload generation, SOPS, or SSH.
- [ ] Invalid expiry exits non-zero before any external mutation.
- [ ] Metadata is constructed with `jq --arg`, not manual JSON interpolation.
- [ ] Date-only and offset inputs produce canonical UTC metadata and output.
- [ ] JSON-breaking expiry input is rejected before remote actions.
- [ ] Focused expiry and audit-hook tests pass.
- [ ] Bash syntax and shellcheck pass.
- [ ] Exactly the two in-scope files are present in the implementation commit.
- [ ] The implementation branch is clean after commit.

## STOP conditions

Stop and report instead of improvising if:

- Either in-scope file no longer matches the excerpts or changed after `7bdba37`.
- The accepted normalizer no longer emits the documented canonical UTC form.
- Fixing bootstrap expiry requires changing the server, schema, long-lived issuer, normalizer, Makefile, dependencies, or documentation.
- A successful test would require a real provider credential, decrypted secret, remote host, or non-hermetic network call.
- A verification command fails twice after one reasonable correction within scope.
- An unrelated pre-existing test failure blocks the focused gates.

## Maintenance notes

- Keep both issuer scripts on the same normalizer and `jq --arg` metadata pattern; do not reintroduce parallel timestamp parsing or string-built JSON.
- Validation ordering is a safety property: any future option that affects remote metadata must be validated before Terraform, payload generation, or SSH.
- Reviewers should verify that the displayed expiry, audit note, and sidecar all derive from the same normalized `EXPIRES` value.
