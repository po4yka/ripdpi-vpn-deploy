# role: runtime-release — shared pinned runtime activation

## Design decisions

**Internal role with a prefixed API** — consumers use `include_role` and pass
only `runtime_release_*` inputs. The role remains inert until a consumer adopts
it; it never appears directly in `site.yml`.

**Canonical architecture key** — gathered `x86_64`/`amd64` and
`aarch64`/`arm64` facts collapse to `amd64` or `arm64`. Consumers provide URLs,
checksums, archive members, and any upstream-specific filename slug under those
two keys.

**Candidate publication and activation share one host-local lock** — the role
downloads and extracts into a private per-pin staging area. The helper then
checks the staged executable, atomically installs it under `releases/<version>`,
claims its receipt, and publishes `current`, the public link, and `previous`
as one compensating transaction.

**Staging and immutable storage are root-only** — fixed no-follow staging,
release directories, candidates, receipts, and public publication parents are
all owned by `root:root`. The role rejects consumer overrides, so an untrusted
runtime identity never controls a pathname that root later writes through.

**Source builds publish from a private transaction** — source consumers provide
a stable project identity, canonical recipe, and staged-to-live output map. The
helper builds below a fixed root-only project directory, verifies every staged
executable and optional digest, then atomically publishes all live outputs with
compensation before recording one typed receipt. Consumer roles own their build
commands, not locking, publication, receipt parsing, or drift classification.

## What's done well

- **Fail-closed input surface** — empty pins, unsupported architectures,
  relative/traversing paths, unsafe names, and unmanaged activation targets are
  rejected before the role creates a directory or downloads an artifact.
- **Rollback links survive upgrades** — after both activation links pass their
  postcheck, `previous` records the observed prior managed release. A failed
  activation therefore cannot consume the older rollback pointer.
- **Exact link compensation** — if a publication or postcheck fails, the
  locked helper restores the observed `current`, public, and `previous` link
  targets (including absence). An unconfirmed restoration has its own
  fail-closed result.
- **Receipts bind pins to installed bytes** — the root-owned receipt records
  artifact and binary SHA256 values. Receipt-less legacy candidates are adopted
  only after a fresh pinned artifact produces byte-identical executable output.
- **Namespace writes retain directory descriptors** — link publication,
  deletion, and compensation use no-follow dirfd-relative operations after
  rechecking the captured parent identity. A renamed public parent fails
  closed instead of redirecting a write.

## Pitfalls

- **Link activation is serialized, not power-loss atomic** — each helper link
  replacement and directory sync is atomic, and ordinary failures are
  compensated under the same lock; sudden host loss between replacements can
  still leave a mixed set for an operator to diagnose.
- **Archive extraction selects one architecture-bound member** — consumers
  provide exact `amd64` and `arm64` members plus at most four stripped path
  components. The selected remaining path must be exactly
  `runtime_release_binary_name`; unrelated members are never extracted.
- **Existing release directories are immutable by receipt** — matching receipt
  and binary digests skip download/extraction. A changed pin or binary refuses
  before writes; version bumps, never in-place replacement, are the update path.
- **The root storage contract is not configurable** — direct helper tests may
  use an unprivileged identity, but the Ansible role rejects any non-root
  storage override before it creates, downloads, extracts, or activates.
- **Fresh check mode is predictive** — it validates inputs and ownership but
  cannot download into a simulated directory. It reports the planned change and
  leaves activation untouched; normal convergence supplies the byte proof.
- **Source-build receipts use a fixed namespace** — the central receipt root,
  staging root, and per-project lock names are not consumer inputs. A consumer
  may describe source identity, commands, staged files, and live outputs, but
  cannot redirect root-owned state outside its private project transaction.
- **Consumer commands remain trusted role code** — the helper strips inherited
  environment and validates absolute executables, working directories, and
  staged/live paths. It does not sandbox an intentionally malicious argv, so
  descriptors must remain repository-authored role inputs.
- **Post-commit cleanup is recovery debt, not rollback** — once live outputs and
  their receipt are durable, failure to remove private staging or backup names
  returns `cleanup_pending` and keeps convergence successful. Consumers expose
  that categorical state; operators must clear the private residue separately.
