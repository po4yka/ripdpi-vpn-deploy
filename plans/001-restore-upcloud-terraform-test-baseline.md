# Plan 001: Restore the UpCloud Terraform test baseline

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` — unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- terraform/providers/upcloud/main.tf terraform/providers/upcloud/tests/server.tftest.hcl`
> If either in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

The repository's pinned Terraform 1.15.2 gate currently fails in the UpCloud root: `mise exec -- make tf-test` reports 12 passed, 3 failed, and 2 skipped before it can test the other providers. Two assertions count all public interfaces even though the contract is specifically about IPv4, so the intended IPv6 interface creates an off-by-one result. The IPv6-disabled assertion also becomes unknown because the permanent public IPv4 interface leaves `ip_address_family` implicit in a mocked plan. Restoring this baseline is a prerequisite for trusting later Terraform changes.

## Current state

- `terraform/providers/upcloud/main.tf` owns the UpCloud server's network-interface blocks.
- `terraform/providers/upcloud/tests/server.tftest.hcl` contains plan-time mock-provider assertions for IPv4, IPv6, metadata, and placeholder rejection.
- The permanent public interface and optional secondary public interface both omit `ip_address_family`; the IPv6 interface explicitly sets it.
- The first two affected tests count every interface whose `type` is `public`, although their names and error messages describe public IPv4 allocation.
- Repository Terraform formatting uses standard `terraform fmt`; native provider tests run through the Makefile with the mise-pinned Terraform version.

Current excerpts:

```hcl
# terraform/providers/upcloud/main.tf:44-63
network_interface {
  type = "public"
}

dynamic "network_interface" {
  for_each = var.enable_ipv6 ? [1] : []
  content {
    type              = "public"
    ip_address_family = "IPv6"
  }
}

dynamic "network_interface" {
  for_each = var.additional_public_ip ? [1] : []
  content {
    type = "public"
  }
}
```

```hcl
# terraform/providers/upcloud/tests/server.tftest.hcl:29-53
condition = length([
  for ni in upcloud_server.vpn.network_interface :
  ni if ni.type == "public"
]) == 1

condition = length([
  for ni in upcloud_server.vpn.network_interface :
  ni if ni.type == "public"
]) == 2
```

Match the existing explicit family spelling already used by the IPv6 block: `ip_address_family = "IPv6"`. Use the provider's corresponding canonical value `"IPv4"` for IPv4 blocks. Keep assertions plan-time and based on the rendered resource, not merely on input variables.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | `git diff --stat 7bdba37..HEAD -- terraform/providers/upcloud/main.tf terraform/providers/upcloud/tests/server.tftest.hcl` | no output |
| Format | `mise exec -- terraform -chdir=terraform/providers/upcloud fmt -check -recursive` | exit 0, no diff reported |
| Initialize | `mise exec -- terraform -chdir=terraform/providers/upcloud init -backend=false` | exit 0 |
| Focused test | `mise exec -- terraform -chdir=terraform/providers/upcloud test` | exit 0; all UpCloud tests pass, with only intentional expected-failure behavior |
| Cross-provider gate | `mise exec -- make tf-test` | exit 0; UpCloud, Hetzner, and Vultr suites pass |
| Worktree check | `git status --short` | only the two in-scope files are modified before commit; clean after commit |

## Scope

**In scope** (the only source files you should modify):

- `terraform/providers/upcloud/main.tf`
- `terraform/providers/upcloud/tests/server.tftest.hcl`

**Out of scope** (do not touch):

- Hetzner or Vultr Terraform roots.
- UpCloud variables, outputs, firewall resources, provider versions, lockfiles, or environment tfvars.
- Shared cloud-init templates.
- `Makefile`, CI workflows, documentation, snapshots, or `CLAUDE.md`; this change makes the existing IPv4 contract explicit and restores its tests, without changing a design decision.
- Any provider upgrade or relaxation of `required_version`.

## Git workflow

- Branch: `codex/advisor-001-upcloud-tf-tests`
- Make one focused Conventional Commit after all gates pass: `fix(terraform): restore upcloud network tests`
- Stage only the two in-scope files.
- Do not push, merge, or open a PR.

## Steps

### Step 1: Make both public IPv4 interfaces explicit

In `terraform/providers/upcloud/main.tf`, add `ip_address_family = "IPv4"` to:

1. The permanent public network interface at lines 44-46.
2. The optional `additional_public_ip` dynamic block at lines 59-63.

Preserve the existing block order: primary IPv4, optional IPv6, optional secondary IPv4, utility. Do not alter any toggle or lifecycle behavior.

**Verify**: `mise exec -- terraform -chdir=terraform/providers/upcloud fmt -check -recursive` → exit 0.

### Step 2: Assert IPv4 and IPv6 independently

In `terraform/providers/upcloud/tests/server.tftest.hcl`, change the two secondary-address assertions so their comprehensions include only interfaces with `type == "public"` and `ip_address_family == "IPv4"`.

Keep the existing expected counts:

- Default: exactly one public IPv4 interface.
- `additional_public_ip = true`: exactly two public IPv4 interfaces.

Preserve the separate IPv6 enabled/disabled tests. Do not weaken an assertion to inspect only input variables or total dynamic-block counts.

**Verify**: `mise exec -- terraform -chdir=terraform/providers/upcloud test` → exit 0 with no failed runs.

### Step 3: Run the cross-provider Terraform gate

Run `mise exec -- make tf-test`. Confirm all three provider roots execute; do not treat a focused UpCloud pass as sufficient.

**Verify**: `mise exec -- make tf-test` → exit 0.

### Step 4: Commit the validated slice

Review `git diff --check` and `git diff -- terraform/providers/upcloud/main.tf terraform/providers/upcloud/tests/server.tftest.hcl`. Stage only those two files and commit with `fix(terraform): restore upcloud network tests`.

**Verify**: `git show --stat --oneline HEAD` lists only the two in-scope files, and `git status --short` is empty.

## Test plan

- Keep all existing cases in `terraform/providers/upcloud/tests/server.tftest.hcl`.
- The default case must distinguish one IPv4 plus one IPv6 from two IPv4 interfaces.
- The opt-in case must distinguish two IPv4 plus one IPv6 from three IPv4 interfaces.
- The IPv6-disabled case must evaluate to a known boolean at plan time and confirm zero IPv6 interfaces.
- The IPv6-default case must continue confirming exactly one IPv6 interface.
- Use the existing mock-provider plan-time tests as the structural pattern; do not replace them with textual source inspection.

## Done criteria

- [ ] Both UpCloud IPv4 network-interface blocks explicitly set `ip_address_family = "IPv4"`.
- [ ] The default and opt-in public-address assertions count only IPv4 interfaces.
- [ ] `mise exec -- terraform -chdir=terraform/providers/upcloud fmt -check -recursive` exits 0.
- [ ] `mise exec -- terraform -chdir=terraform/providers/upcloud test` exits 0.
- [ ] `mise exec -- make tf-test` exits 0 for all provider roots.
- [ ] Exactly the two in-scope files are present in the implementation commit.
- [ ] The implementation branch is clean after the commit.

## STOP conditions

Stop and report instead of improvising if:

- Either in-scope file no longer matches the excerpts or changed after `7bdba37`.
- The UpCloud provider rejects `ip_address_family = "IPv4"` on either public-interface block.
- Restoring the tests requires a provider, Terraform, lockfile, variable, output, or CI change.
- Any cross-provider test fails for a reason not caused by the two-file change.
- A verification command fails twice after one reasonable correction within scope.
- Any secret, state file, real plan, provider credential, or non-mocked cloud operation becomes necessary.

## Maintenance notes

- Future UpCloud network-interface changes must keep address-family assertions family-specific; total `type == "public"` counts combine IPv4 and IPv6 and do not express the secondary-IPv4 contract.
- Reviewers should confirm this remains a declarative no-op for existing intent: it makes the provider's implicit IPv4 default explicit and does not add or remove interfaces.
- Do not paper over future mock-provider unknown values with `try`, `can`, or input-only assertions; resource-shape tests should remain able to catch unintended provider configuration changes.
