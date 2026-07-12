# Plan 009: Serialize and validate cloud-init inputs structurally

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8fc8536..HEAD -- terraform/shared/cloud-init.yaml.tftpl terraform/shared/CLAUDE.md scripts/render-cloud-init-ci.py tests/unit/test_cloud_init_marker.py terraform/providers/hetzner/main.tf terraform/providers/hetzner/variables.tf terraform/providers/hetzner/tests/server.tftest.hcl terraform/providers/upcloud/main.tf terraform/providers/upcloud/variables.tf terraform/providers/upcloud/tests/server.tftest.hcl terraform/providers/vultr/main.tf terraform/providers/vultr/variables.tf terraform/providers/vultr/tests/server.tftest.hcl`
> If any existing in-scope file changed since the Plan 001 integration commit, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/001-restore-upcloud-terraform-test-baseline.md` (`8fc8536`)
- **Category**: correctness
- **Planned at**: integration commit `8fc8536`, 2026-07-11

## Why this matters

Every provider currently inserts operator-controlled username, SSH-key, and build-label strings directly into YAML scalars. Punctuation can make otherwise reasonable input render incorrectly, while carriage returns or newlines can alter the cloud-init document instead of failing at Terraform validation. All three provider roots must encode scalar fragments structurally, reject values that violate their operating-system and line-oriented contracts, and prove the decoded user-data preserves the original values.

## Current state

- `terraform/shared/cloud-init.yaml.tftpl:7-16` interpolates the admin username and public key as raw YAML:

```yaml
users:
  - default
  - name: ${admin_user}
    gecos: VPN Deploy User
    groups: [sudo]
    shell: /bin/bash
    lock_passwd: true
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    ssh_authorized_keys:
      - ${admin_ssh_public_key}
```

- `terraform/shared/cloud-init.yaml.tftpl:40-46` interpolates the build label inside a block scalar:

```yaml
  - path: /etc/vpn-build-id
    owner: root:root
    permissions: "0644"
    content: |
      provisioned_by=cloud-init
      next_stage=ansible
      build_env=${build_env}
```

- Each provider's `main.tf:1-6` passes raw values with the same map:

```hcl
user_data = templatefile("${path.module}/../../shared/cloud-init.yaml.tftpl", {
  admin_user           = var.admin_user
  admin_ssh_public_key = var.admin_ssh_public_key
  build_env            = var.build_env
})
```

- `terraform/providers/{hetzner,upcloud,vultr}/variables.tf` defines `admin_user`, `admin_ssh_public_key`, and `build_env` without validation. The build-label description calls it free-form even though it is also used in provider labels/tags and `/etc/vpn-build-id`.
- Hetzner and Vultr `tests/server.tftest.hcl` only search rendered text for fixture substrings. UpCloud has no user-data assertion. Use Terraform's `yamldecode()` against the actual provider resource as the structural regression pattern; do not substitute a source-text assertion.
- `scripts/render-cloud-init-ci.py` uses a generic `${name}` regex and raw replacement. It must render the same pre-encoded placeholder contract as Terraform without implementing a general Terraform expression evaluator. Python's `json.dumps()` is acceptable for emitting YAML-compatible quoted scalars because JSON strings are valid YAML scalars and preserve punctuation/newlines exactly.
- `tests/unit/test_cloud_init_marker.py` already invokes the renderer and parses its output with `yaml.safe_load`. Extend this test surface to assert the decoded username, key, and build-file content, including punctuation that would be YAML-significant if inserted raw.
- `terraform/shared/CLAUDE.md` is the nearest design record. Add the durable rule that all template inputs are pre-encoded scalar fragments and all new inputs must be structurally serialized plus validated at every provider boundary.
- Repository conventions: use `terraform fmt`; keep provider variable contracts identical; use mock-provider `terraform test` assertions; run `make validate` before committing Terraform changes; do not edit lockfiles, examples, provider versions, or generated state.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output on the Plan 001 integration base |
| Python regression | `mise exec -- python3 -m pytest tests/unit/test_cloud_init_marker.py -q` | all tests pass |
| Cloud-init schema | `mise exec -- make cloud-init-schema` | rendered config is valid cloud-config |
| Terraform format | `for provider in upcloud hetzner vultr; do mise exec -- terraform -chdir=terraform/providers/$provider fmt -check -recursive || exit 1; done` | exit 0, no format diff |
| Cross-provider Terraform tests | `mise exec -- make tf-test` | all UpCloud, Hetzner, and Vultr tests pass |
| Required repository gate | `mise exec -- make validate` | exit 0, or only the unchanged documented historical gitleaks baseline after all non-gitleaks components pass |
| Commit-scoped secret scan | after commit, `mise exec -- gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |
| Diff hygiene | `git diff --check` | exit 0, no output |

## Scope

**In scope** (the only source/test files you may modify):

- `terraform/shared/cloud-init.yaml.tftpl`
- `terraform/shared/CLAUDE.md`
- `scripts/render-cloud-init-ci.py`
- `tests/unit/test_cloud_init_marker.py`
- `terraform/providers/hetzner/main.tf`
- `terraform/providers/hetzner/variables.tf`
- `terraform/providers/hetzner/tests/server.tftest.hcl`
- `terraform/providers/upcloud/main.tf`
- `terraform/providers/upcloud/variables.tf`
- `terraform/providers/upcloud/tests/server.tftest.hcl`
- `terraform/providers/vultr/main.tf`
- `terraform/providers/vultr/variables.tf`
- `terraform/providers/vultr/tests/server.tftest.hcl`

**Out of scope** (do not modify):

- Provider resources other than the `templatefile` input map, outputs, firewall behavior, network-interface behavior, lifecycle rules, provider versions, lockfiles, Terraform state, or environment tfvars/examples.
- Cloud-init packages, SSH-hardening commands, completion-marker behavior, file paths, owners, permissions, or the exact three-line `/etc/vpn-build-id` content.
- SSH key generation, key-material normalization, accepting multiline authorized-key options, or restricting the repository to one SSH algorithm. Preserve valid single-line OpenSSH public keys with an optional comment.
- A general YAML renderer, template engine, or cross-provider Terraform module refactor.
- Any real username, hostname, public key, credential, provider token, state, or plan artifact in fixtures or commits.
- `Makefile`, CI workflows, `CHANGELOG.md`, and unrelated documentation or tests.

## Git workflow

- Start from branch/commit `codex/advisor-001-upcloud-tf-tests` at `8fc8536` so the completed Terraform baseline is present.
- Create/switch to branch `codex/advisor-009-structure-cloud-init-yaml` in the isolated executor worktree.
- Create one focused Conventional Commit: `fix(terraform): structure cloud-init values`.
- Do not push, merge, cherry-pick, or open a pull request.

## Steps

### Step 1: Pre-encode every dynamic YAML scalar

Rename the three shared template placeholders so their contract is unmistakably pre-encoded: `admin_user_yaml`, `admin_ssh_public_key_yaml`, and `build_id_content_yaml`. Keep the existing YAML document shape, but place the encoded values at scalar positions:

- `name: ${admin_user_yaml}`
- `- ${admin_ssh_public_key_yaml}`
- replace the literal block under `/etc/vpn-build-id` with `content: ${build_id_content_yaml}`

In all three provider `main.tf` files, pass `yamlencode(var.admin_user)`, `yamlencode(var.admin_ssh_public_key)`, and `indent(4, yamlencode(format("provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=%s\n", var.build_env)))` under those renamed keys. The four-space `indent()` is load-bearing: Terraform emits the multiline string as a YAML block scalar whose continuation lines already have two spaces, and the template places the first line after a key indented four spaces; adding four spaces to every continuation line makes them six-space children of that key. Do not use raw interpolation, string escaping by hand, or `replace()` as a serialization substitute. Keep the three-line build-file content and trailing newline semantically identical after `yamldecode()`.

Update `render-cloud-init-ci.py` to construct exactly those three pre-encoded fixture values with `json.dumps()` and retain a narrow literal-placeholder substitution. Make unknown or unexpanded placeholders fail loudly instead of silently emitting an incomplete config. Use a punctuation-bearing, non-secret fixture comment such as `operator: ci # fixture` so the schema gate exercises YAML-significant characters.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_cloud_init_marker.py -q && mise exec -- make cloud-init-schema` → the decoded fixture values match exactly and cloud-init accepts the rendered document.

### Step 2: Add identical provider-boundary validation

Add the same validation blocks to the three provider `variables.tf` files:

1. `admin_user` must match a conservative Linux login name: starts with a lowercase ASCII letter or underscore, continues only with lowercase ASCII letters, digits, underscores, or hyphens, and is at most 32 characters total. Reject whitespace, colons, shell punctuation, CR, and LF.
2. `admin_ssh_public_key` must be non-empty, equal to its own `trimspace()` result, contain no CR or LF, and have a single-line OpenSSH public-key shape: non-whitespace key type, non-whitespace encoded key body, and an optional comment after one or more spaces. Do not overfit validation to `ssh-ed25519`; existing RSA, ECDSA, and security-key public-key types must remain valid. Do not expose the sensitive value in error text.
3. `build_env` must be a technical label of 1–64 characters: begin with an ASCII alphanumeric character and continue only with ASCII alphanumerics, underscores, or hyphens. Update its description to remove "Free-form" and describe the exact label contract.

Keep the blocks textually and semantically identical across all providers. If Terraform's validation language makes the optional SSH comment ambiguous, prefer the narrow contract above and add positive tests for at least two key types rather than inventing key decoding.

**Verify**: run the Terraform format command from the table → all three roots are formatted and unchanged by a second `terraform fmt` check.

### Step 3: Prove structural rendering and negative inputs in every provider

Update each provider's `tests/server.tftest.hcl` using its actual user-data resource (`hcloud_server.vpn.user_data`, `upcloud_server.vpn.user_data`, or `vultr_instance.vpn.user_data`). Add or strengthen a positive run that:

- Overrides the SSH fixture with a safe single-line key whose comment includes YAML-significant punctuation such as a colon and hash.
- Calls `yamldecode()` on the resource's rendered user-data.
- Asserts `users[1].name` equals the input username exactly.
- Asserts `users[1].ssh_authorized_keys[0]` equals the full public key exactly, including punctuation.
- Selects the `/etc/vpn-build-id` entry from `write_files` and asserts its decoded `content` is exactly `provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=test\n`.

Add expected-failure runs for invalid `admin_user`, multiline `admin_ssh_public_key`, and newline-bearing `build_env` in each provider root, with `expect_failures` naming the corresponding variable. Keep existing resource/network/output assertions intact. Tests must prove provider-local validation rather than relying on one provider as a proxy for the duplicated contract.

**Verify**: `mise exec -- make tf-test` → every run in all three roots passes, including the expected variable failures.

### Step 4: Record the serialization boundary and strengthen the Python regression

Update `terraform/shared/CLAUDE.md` without changing its three-section structure. Record under Design decisions that the template accepts only pre-encoded YAML scalar fragments from provider roots, and under Pitfalls that new dynamic values require both structural encoding and identical validation in every provider. Keep each new paragraph as one logical line rather than hard-wrapping it.

Extend `tests/unit/test_cloud_init_marker.py` so the renderer regression parses the document and asserts all three decoded values, including the punctuation-bearing SSH comment and exact build-file content. Preserve the completion-marker failure/success assertions. It is acceptable to extract a small rendering helper in the script if that makes the contract directly testable, but do not broaden it into a general-purpose template engine.

**Verify**: `mise exec -- python3 -m pytest tests/unit/test_cloud_init_marker.py -q && mise exec -- make cloud-init-schema` → all focused tests and schema validation pass.

### Step 5: Run the repository gate and commit normally

Run `mise exec -- make validate` because this change touches Terraform and Python. Do not skip or suppress any hook or scanner. The repository may stop at two unchanged historical gitleaks findings outside this plan; if and only if that exact baseline reproduces, require the Terraform fmt/validate loop, `ansible-lint`, and site syntax check to pass individually and run the commit-scoped gitleaks scan after the normal hooked commit. Any new leak, Terraform validation failure, Ansible failure, or different aggregate failure is a STOP.

Run `git diff --check`, inspect the full diff, and confirm exactly the thirteen in-scope files. Commit normally with hooks enabled using `fix(terraform): structure cloud-init values`, then run the commit-scoped gitleaks command and confirm the executor worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the thirteen in-scope files, `git status --short` has no output, and the scoped gitleaks scan exits 0.

## Test plan

- Python parses the real shared template rendered with punctuation-bearing fixture values and proves YAML semantics, exact build-file content, and unchanged completion-marker ordering.
- Each provider mock test parses the actual resource user-data with `yamldecode()` and proves the provider's template map preserves username, SSH key, and build-file content.
- Each provider independently rejects an invalid login name, a multiline SSH key, and a newline-bearing environment label through `expect_failures`.
- Existing provider network, output, backup, metadata, and secondary-address tests remain unchanged and pass.
- `make cloud-init-schema` proves the CI renderer and cloud-init agree on the resulting document.
- `make validate` proves Terraform formatting/validation and the repository's normal lint/security gates.

## Done criteria

- [ ] The shared template has no raw `${admin_user}`, `${admin_ssh_public_key}`, or `${build_env}` interpolation and accepts only the three explicitly pre-encoded scalar placeholders.
- [ ] Hetzner, UpCloud, and Vultr use `yamlencode()` for all three dynamic cloud-init values, apply the required four-space `indent()` to the multiline build-content fragment, and preserve the exact `/etc/vpn-build-id` content.
- [ ] All three provider roots carry identical validation for username, single-line public key, and technical build label.
- [ ] All three resource user-data tests use `yamldecode()` and preserve YAML-significant SSH-comment punctuation exactly.
- [ ] All three provider roots have expected-failure coverage for invalid username, multiline key, and newline-bearing build label.
- [ ] `mise exec -- python3 -m pytest tests/unit/test_cloud_init_marker.py -q` passes.
- [ ] `mise exec -- make cloud-init-schema` passes.
- [ ] `mise exec -- make tf-test` passes for all three provider roots.
- [ ] `mise exec -- make validate` passes, or its only aggregate failure is the unchanged documented historical gitleaks baseline while all non-gitleaks components and the commit-scoped scan pass.
- [ ] `git diff --check` passes; exactly thirteen in-scope files are committed; the executor reports the commit SHA; the executor worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any existing in-scope file drifted from integration commit `8fc8536`, including the Plan 001 UpCloud network/test changes.
- `yamlencode()` scalar fragments do not decode to the exact original values through both Terraform `yamldecode()` and Python `yaml.safe_load()`.
- Preserving the exact three-line build-file content requires changing cloud-init paths, ownership, permissions, or first-boot commands.
- A checked-in environment example uses a username or build label outside the specified validation contract, or a valid supported single-line OpenSSH public-key type cannot pass the general validation.
- Provider-local validation cannot be kept identical without a broader module refactor.
- `make cloud-init-schema` or any provider test requires credentials, live resources, state, or a non-mocked operation.
- `make validate` produces a new/different failure, normal commit hooks fail, or any gate fails twice after a reasonable in-scope correction.
- The implementation requires modifying a fourteenth file or any out-of-scope behavior.

## Maintenance notes

The template placeholder suffix `_yaml` is a contract, not cosmetic naming: callers must pass a structurally encoded scalar, never raw operator input. When a future provider or cloud-init value is added, update every provider's template map and variable validation together, then prove the decoded resource user-data rather than matching rendered substrings. Reviewers should scrutinize exact decoded values and reject hand-written escaping, because escaping rules are easy to get subtly wrong across YAML and Terraform.
