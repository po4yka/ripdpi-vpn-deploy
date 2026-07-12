# Plan 008: Bind destroy authorization to the state-backed resource identity

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- scripts/destroy.sh scripts/CLAUDE.md tests/unit/test_destroy_ci_mode.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: correctness
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`scripts/destroy.sh` asks the operator to type the desired hostname from the selected tfvars file before Terraform has rendered a destroy plan. If the selected workspace contains stale, restored, or misrouted state, that prompt can pass while the plan deletes a different real server at the same generic resource address. Authorization must instead be bound to the hostname/name and immutable provider ID in the server resource's `change.before` object, and every deleted address must belong to the expected provider root.

## Current state

- `scripts/destroy.sh:24-29` maps providers to one canonical server resource address:

```bash
upcloud) DESTROY_RESOURCE="upcloud_server.vpn" ;;
hetzner) DESTROY_RESOURCE="hcloud_server.vpn" ;;
vultr) DESTROY_RESOURCE="vultr_instance.vpn" ;;
```

- Lines 65-80 extract `server_name` from desired tfvars and complete the hostname/`DESTROY` prompts before creating the override or plan:

```bash
expected="$(grep -E '^server_name' "$TFVARS" | head -1 | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/')"
read -r -p "Type the server hostname to confirm (Ctrl-C to abort): " typed
```

- Lines 95-105 render the destroy plan and validate only that the provider-generic server address has a delete action. The plan's `.change.before` identity and the remaining delete addresses are not inspected.
- Provider identity fields in current Terraform resources are:
  - UpCloud `upcloud_server.vpn`: `.change.before.hostname` plus `.change.before.id`.
  - Hetzner `hcloud_server.vpn`: `.change.before.name` plus `.change.before.id`.
  - Vultr `vultr_instance.vpn`: `.change.before.hostname` plus `.change.before.id`.
- Provider roots contain these legitimate delete address families:
  - UpCloud: `upcloud_server.vpn`, `upcloud_firewall_rules.vpn`.
  - Hetzner: `hcloud_server.vpn`, `hcloud_ssh_key.admin`, `hcloud_firewall.vpn`, `hcloud_firewall_attachment.vpn`, optional `hcloud_floating_ip.honeypot_ipv4[0]`.
  - Vultr: `vultr_instance.vpn`, `vultr_ssh_key.admin`, `vultr_firewall_group.vpn`, optional `vultr_instance_ipv4.honeypot[0]`, and keyed instances of `vultr_firewall_rule.icmp`, `.ssh`, and `.tcp_public`.
- `tests/unit/test_destroy_ci_mode.py` copies `destroy.sh` and `terraform-env.sh` into a temporary repo, stubs Terraform, and currently emits plan JSON containing only an address/actions pair. Extend this harness to emit full fixture JSON with `change.before` identity and arbitrary resource changes.
- `scripts/CLAUDE.md` currently says destroy is provider-aware and plan-verified, but it describes only address checking. Update that durable contract after the implementation.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Bash syntax | `bash -n scripts/destroy.sh` | exit 0 |
| Focused ShellCheck | `shellcheck -s bash -S warning scripts/destroy.sh` | exit 0, no warnings |
| Focused regression | `mise exec -- python3 -m pytest tests/unit/test_destroy_ci_mode.py tests/unit/test_terraform_env.py -q` | all pass |
| Repository shell gate | `mise exec -- make shellcheck` | all shell scripts pass |
| Diff hygiene | `git diff --check` | exit 0, no output |
| Commit-scoped secret scan | after commit, `mise exec -- gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- `scripts/destroy.sh`
- `tests/unit/test_destroy_ci_mode.py`
- `scripts/CLAUDE.md`

**Out of scope** (do not modify):

- Terraform resources, provider outputs, `terraform-env.sh`, Makefile, workflows, runbooks, inventory format, or state files.
- Changing `prevent_destroy`, the temporary override resource, provider support, CI environment restrictions, apply command, inventory cleanup timing, or post-destroy messaging.
- Automatically accepting a desired/planned identity mismatch, inventing a force flag, or allowing unknown delete addresses.
- Printing full plan JSON, IP addresses, user data, labels, credentials, or other state attributes. Display only provider, canonical resource address, planned hostname/name, and immutable ID.
- Parsing binary tfplan data directly; use `terraform show -json` once and a private temporary JSON file.

## Git workflow

- Branch: `codex/advisor-008-bind-destroy-identity`
- Create one focused Conventional Commit: `fix(scripts): bind destroy to planned identity`.
- Do not push, merge, or open a pull request.

## Steps

### Step 1: Render and securely capture the plan before authorization

Keep the initial danger banner, provider/root/tfvars checks, CI environment restriction, override generation, and Terraform plan command. Move all interactive authorization prompts until after the plan is rendered and validated.

Create a private temporary file with portable `mktemp -t ...XXXXXX`, set mode `0600`, and write exactly one `terraform show -json` result into it. Extend the existing EXIT trap to remove the override and temporary JSON on every exit; keep the existing tfplan cleanup semantics unless changing them is necessary for a meaningful test. A failed show must stop before identity parsing or apply.

Extract the desired tfvars hostname only for comparison/display; require it to be non-empty and never use it as the primary interactive confirmation value.

**Verify**: Bash syntax and focused ShellCheck pass.

### Step 2: Validate the complete provider-specific delete contract

Using `jq` against the captured plan JSON, require exactly one resource change at `DESTROY_RESOURCE` whose actions contain `delete`. From that same change, extract the provider-specific state-backed identity field and `.change.before.id`; convert scalar IDs to strings but reject null, empty, objects, arrays, and Terraform unknown placeholders.

Collect every resource address whose actions contain `delete` and reject the plan if any address is outside the provider allowlist documented above. Match optional/indexed addresses narrowly:

- Hetzner floating IP only as `hcloud_floating_ip.honeypot_ipv4[0]`.
- Vultr optional IPv4 only as `vultr_instance_ipv4.honeypot[0]`.
- Vultr firewall rules only as keyed instances of the three exact resource names; do not allow arbitrary `vultr_*` prefixes.

Require the canonical server delete even if every other address is allowed. Reject duplicate server changes, missing `before`, missing identity, missing ID, create/update-only server actions, malformed plan roots, and unexpected delete addresses. Diagnostics may name offending resource addresses but must not dump `before` objects.

Display a concise review block containing only provider, environment, canonical address, planned hostname/name, immutable ID, and desired tfvars hostname.

**Verify**: focused tests for all providers and malformed/unexpected plans pass.

### Step 3: Bind interactive and CI authorization to the planned identity

Define one exact confirmation token derived from the plan identity, for example `<planned-hostname>#<immutable-id>`, and display it only in the prompt/review block.

Interactive behavior:

1. If desired tfvars hostname differs from the planned hostname/name, print a high-visibility warning showing both values and require the literal `STATE-MISMATCH` before continuing. A wrong response stops before apply.
2. Require the operator to type the exact plan-derived confirmation token. Typing only the desired hostname or the planned hostname without the immutable ID must fail.
3. Preserve the existing literal `DESTROY` prompt and final `[yes/NO]` apply prompt after identity confirmation.

Non-interactive CI behavior:

- Preserve the validated `ci-*` environment restriction.
- Require the desired tfvars hostname to equal the planned hostname/name and require a non-empty immutable ID; otherwise stop before apply because no human can review the mismatch.
- Log authorization using only the CI environment, canonical resource, planned hostname/name, and immutable ID.

Do not add a general force/override flag. Interactive `STATE-MISMATCH` plus exact state identity is the explicit manual recovery path.

**Verify**: tests prove desired-hostname input cannot authorize a mismatched planned resource, exact planned hostname plus ID can authorize after mismatch acknowledgement, and CI mismatch fails.

### Step 4: Build exploit-shaped hermetic regressions

Refactor the Terraform stub in `tests/unit/test_destroy_ci_mode.py` to emit JSON from a per-test file/environment variable. Provide helpers that construct provider-specific server changes with identity and ID plus optional additional deletes.

Retain every existing behavior test and add at least:

1. Parameterized successful CI destruction for UpCloud, Hetzner, and Vultr using their correct identity fields and non-empty IDs.
2. CI desired/planned hostname mismatch refuses apply.
3. Missing/null/empty immutable ID refuses apply.
4. Wrong provider identity field refuses apply.
5. Duplicate canonical server changes refuse apply.
6. Canonical server change without delete refuses apply.
7. One unexpected delete address alongside the valid server refuses apply and names the address.
8. Allowed optional/indexed/for-each delete addresses for each provider are accepted.
9. Interactive mismatch: input containing only desired hostname fails; input sequence `STATE-MISMATCH`, exact plan identity token, `DESTROY`, `yes` reaches apply.
10. Temporary plan JSON and override are removed after both refusal and success; failed apply still preserves inventory.

Assert the Terraform log contains no apply command on every refusal. Do not include actual provider IDs, hostnames, IPs, or credentials; use obvious test-only placeholders.

**Verify**: focused pytest passes.

### Step 5: Record the durable contract and commit

Update the existing destroy design-decision line in `scripts/CLAUDE.md` without hard-wrapping new prose: destroy authorization is bound to the planned state identity and ID, the full delete set is provider-allowlisted, CI mismatches fail closed, and interactive mismatch recovery is explicit.

Run Bash syntax, focused/full ShellCheck, focused pytest, and diff hygiene. Confirm exactly the three in-scope files changed. Commit normally with hooks enabled using `fix(scripts): bind destroy to planned identity`; never use `--no-verify` or a skip variable. Run the commit-scoped gitleaks scan and confirm the worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the three files and `git status --short` has no output.

## Test plan

- Stub `terraform show -json` with realistic provider-specific `change.before` identity fields and IDs.
- Assert refusal through absence of `apply`, not only nonzero status or an error substring.
- Exercise all provider allowlists, including indexed and keyed addresses.
- Exercise real stdin prompt sequences for both mismatch refusal and explicit recovery authorization.
- Confirm private temporary JSON cleanup without reading or logging its full contents.
- Keep existing CI workflow/source assertions unchanged.

## Done criteria

- [ ] All confirmation happens after a successfully captured and validated destroy plan.
- [ ] The server resource's state-backed hostname/name and immutable ID are extracted from the exact delete change and form the interactive confirmation token.
- [ ] Every delete address is provider-allowlisted; duplicate/malformed/missing server identity and unexpected resources fail before apply.
- [ ] Interactive tfvars/state mismatch requires `STATE-MISMATCH` plus exact planned hostname/name and ID; CI mismatch always fails.
- [ ] Plan JSON is mode `0600`, never dumped, and removed on every exit.
- [ ] Existing apply failure/inventory preservation and provider-specific override behavior remain green.
- [ ] Focused pytest, Bash syntax, focused/full ShellCheck, diff hygiene, normal commit hooks, and scoped gitleaks pass.
- [ ] Exactly three in-scope files are committed; worktree clean; executor reports commit SHA.

## STOP conditions

Stop and report instead of improvising if:

- Any in-scope file drifted from `7bdba37`.
- Real Terraform plan fixtures show a provider identity field or ID shape different from the documented contract.
- A legitimate current provider resource address is missing from the allowlist and confirming it requires changing Terraform or another file; report the exact address rather than broadening patterns speculatively.
- Terraform emits multiple canonical server instances for a supported topology.
- The fix requires exposing full `before` state, adding a force flag, or weakening CI mismatch refusal.
- Meaningful tests require real Terraform state/provider credentials or cannot remain hermetic.
- A verification or normal commit hook fails twice after a reasonable in-scope correction.
- The implementation requires modifying a fourth file.

## Maintenance notes

Whenever a Terraform root adds, renames, indexes, or keys a managed resource, update the destroy allowlist and provider-specific tests in the same change. Never replace the narrow allowlist with a provider prefix wildcard. The tfvars hostname remains useful context but is not proof of what state will be destroyed; the `change.before` identity and immutable ID are authoritative.
