# role: runtime-release — shared pinned runtime activation

## Design decisions

Hysteria ECH keys are complete consumer authority. Candidate leases allow only the exact additional ech.key file and relocate LoadCredential into their own unique unit. Receipt, interrupted cleanup, retirement and rollback retain the same key/config/unit generation. Native probes consume public configuration derived from the selected private key and never enable insecure TLS.
ECH probes use the semantic companion installed with the controller before candidate admission. They do not load the frontend validator's still-accepted older companion. An isolated-interpreter regression exercises this layout with a stale frontend helper.

`TrustedDirectory` owns directory traversal: transactions retain its scopes with
`ExitStack.enter_context` until publication and compensation finish. Borrowed
parent descriptors stay open for the whole transaction; callers never close them.

Ephemeral Hysteria validation units are root-private `0600`: only PID1 needs their assembled admission configuration. Exact lease inspection rejects a public unit even when its recorded inode and digest match; native process-death recovery verifies the private mode before cleanup.

Retirement accepts `runtime_retire_file_owners` only for declared regular files. Root ownership stays valid; the named producer account is an additional exact-file owner. Root ancestry, mode and single-link checks remain mandatory. Revalidate after stopping producers before deletion. Direct validator callers send both `paths` and `owners`.

**Hysteria candidates retain the destination boundary** — semantic YAML validation requires exactly the fixed guarded SOCKS outbound and rejects ACL or resolver substitutions. A parser-valid config cannot restore an unguarded direct route. Native runtime and full frontend tests remain separate from configuration shape checks.

**Hysteria semantic validation has one companion source** — the Hysteria
consumer installs `scripts/transport_semantics.py` beside the shared YAML
validator. Repository execution resolves that canonical source; installed
execution imports its sibling. The same proxy/origin rules apply before
mutation and before config publication. Other profiles do not import an
unneeded Hysteria companion.


**Shared YAML syntax gate** — `files/validate_yaml_mapping.py` is the bounded,
duplicate-key rejecting validator for transport formats that have no safe
native check command. Consumers install the same helper and select a strict
role-specific semantic profile; native validators remain authoritative where
present.

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

**Candidates are typed by final mode** — consumers select only executable
`0755` binaries or read-only `0644` runtime assets. The locked helper validates
the matching staged shape and publishes the exact configured mode.

**Source builds publish from a private transaction** — source consumers provide
a stable project identity, canonical recipe, and staged-to-live output map. The
helper builds below a fixed root-only project directory, verifies every staged
executable and optional digest, then atomically publishes all live outputs with
compensation before recording one typed receipt. Consumer roles own their build
commands, not locking, publication, receipt parsing, or drift classification.

**The receipt is the source-build commit point** — before any live replacement,
the helper fsyncs private output nodes, exact backups, and an immutable
create-if-absent write-ahead journal. Recovery classifies the receipt as the
exact previous or next document, then performs only rollback or committed
cleanup. A third receipt state refuses without mutating any inode.

**Consumer acceptance is distinct from byte acquisition** — `runtime_release_stage_only` installs the verified immutable candidate and its byte receipt while leaving current/public/previous links unchanged. Protected frontends select complete link/config/TLS/asset plans through `transport_runtime_transaction.py`. Its retained directory descriptors, root-only inode journal and shared consumer lock bind publication to native parser and authenticated frontend traffic; the guarded-generation controller remains the only lifecycle owner. Interrupted intent compensates exact original inodes, while an exact committed receipt retries owned cleanup and readiness. Previous distinct authority survives unchanged retries.

Site retirement contributes exact absence candidates to the final complete frontend plan, including when all frontends are disabled. Timer asset refresh and operator rollback refuse an open outer route owner before recovery or publication. Native admission leases bind the Linux boot identity: a proven reboot permits missing volatile unit/namespace authority only after the new manager confirms no same-named unit or process; durable private files still require their exact inode claims.

**Operator runtime rollback plans only runtime-publisher-owned nodes** — `runtime_candidates` in `transport_runtime_rollback.py` retargets both `XRAY_RUNTIME_BINARY` and `ExecStart` of `xray.service` (and the bundled GeoIP release when the unit uses it) together with the release, asset and public links and the config, after verifying each retained release receipt and digest. The accepted receipt claims every candidate by inode and digest, so the egress-owned private gateway units are never candidates: claiming a unit the egress transaction rewrites would make the next ordinary converge refuse with `accepted-authority-changed`. Gateways keep the pinned release until the pin changes and a deploy re-renders them. Portable tests pin the candidate set and that boundary; the native lane asserts the rolled-back unit text, the live `MainPID` executable, that the published receipt claims no `ripdpi-transport-*.service` node, and that a following converge with the newer pin restores the upgraded release and `MainPID` executable, with the rolled-back release as `previous`.

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

**Backup authority follows selected paths** — the private backup map binds retained original inodes independently of the previous full receipt. Partial plans keep untouched claims; preparation, cleanup and compensation accept only their recorded old/new map states. Existing bootstrap parameters participate in this ownership boundary even before the first accepted frontend.

Staged includes return `runtime_release_candidates` for their own consumer. They never append to a global transport plan; Xray and Hysteria append their returned selections explicitly. Private publication-storage directories also hold a nonblocking shared inspection or exclusive writer lock across independent consumers. Exact legacy symlink preimages may be relative and are restored verbatim; all new candidate targets remain absolute.

## Pitfalls

- **Link activation is serialized, not power-loss atomic** — each helper link
  replacement and directory sync is atomic, and ordinary failures are
  compensated under the same lock; sudden host loss between replacements can
  still leave a mixed set for an operator to diagnose.
- **Archive extraction selects one architecture-bound member** — consumers
  provide exact `amd64` and `arm64` members plus at most four stripped path
  components. The selected remaining path must be exactly
  `runtime_release_binary_name`; unrelated members are never extracted.
- **One include publishes one archive member** — a consumer that needs a
  binary plus bundled data includes the role once per member under separate
  install roots so each receipt and activation link remains single-purpose.
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
- **Build cancellation owns the foreground process group** — SIGINT, SIGTERM,
  timeouts, direct exceptions, and a leader that exits with same-group children
  terminate and reap that private session before the project lock is released.
  Repository-authored build commands must stay foreground: `setsid`, `setpgrp`,
  double-fork, and daemon modes escape portable process-group containment and
  are outside this helper's trusted-command contract.
- **Post-commit cleanup is recovery debt, not rollback** — staging is emptied
  through its retained directory descriptor before the receipt commit. The
  immutable private journal binds previous/next receipts and exact before/after
  output inodes; cleanup failure returns `cleanup_pending` only while that
  journal remains readable, and later convergence retries under the same lock.
- **Readable committed journals notify at least once** — a retry that recovers
  an exact next receipt and all published output identities reports
  `changed=true`, so handlers still run when the original helper died before
  Ansible received its result. A process death after the journal was fully
  removed but before stdout is acknowledged cannot be distinguished from a
  completed prior run and is an accepted process-death boundary.
- **The host UID is a trust boundary** — the project lock serializes every
  authorized writer, and receipt/output parents reject group/world writes. A
  malicious process with that exact UID (root on managed hosts) can still race
  POSIX pathname deletion and is outside the threat model; portable `unlinkat`
  has no expected-inode compare-and-delete operation. Detectable substitutions
  are preserved as manual-recovery evidence rather than removed.

- `tasks/retire.yml` is a consumer-selected lifecycle entry point. Consumers
  declare their exact runtime units and authority paths; it stops installed units,
  refuses foreign owners and removes that set. It never deletes shared packages,
  runtime release receipts or durable recovery/backup state.

Retirement and authority rollback query every declared service, timer and target
directly. `service_facts` enumerates services and cannot prove timer state; the
bounded metadata helper emits only existence and active/enabled flags.

Complete file/ancestor/descendant ownership validation precedes any unit stop.
Symlinks are never traversed during retirement, unsafe shared parents and
foreign children refuse before lifecycle changes, and broad system roots are
not retirement targets. Consumers should declare exact authority files while
retaining unrelated configuration children and inactive evaluation payloads.

Exact consumer backups and staged nodes live in root-only `.ripdpi-transport-runtime` directories beside each selected path. The central journal claims both the private directory and its live parent inode; mount admission refuses mounted leaf replacements. This keeps hardlinks and renames within the same systemd writable bind mount while preserving exact rollback inodes. Unknown directory replacements never authorize cleanup.

Predictive and inspection transactions hold shared locks; only an exclusive live publisher lock permits unfinished generation admission. A reader never grants process-start authority to a pending candidate.
