# tests — coverage matrix

## Layers

| Layer | What | Where | Speed |
|-------|------|-------|-------|
| Unit | Python validators + Jinja-render assertions | `tests/unit/` (pytest) | seconds |
| Snapshot | Golden Jinja renders for every template | `tests/snapshot/` | seconds |
| Schema | `validate-secrets.py` jsonschema | `tests/unit/test_secrets_schema.py` | seconds |
| Molecule (role) | Per-role Ansible scenario in Docker | `ansible/roles/<role>/molecule/` | ~1 min/role |
| Molecule (full-stack) | `site.yml` end-to-end | `ansible/molecule/full-stack/` | ~10 min |
| TF test | `mock_provider` plan-shape tests | per `terraform/providers/<name>/` | seconds |
| CI ephemeral deploy | Label-gated real UpCloud deploy | `.github/workflows/` + `docs/CI-REAL-DEPLOY.md` | ~15 min |

## Design decisions

Bootstrap failure regressions execute ECH refusal, encryption failure and termination with synthetic tool authority and require plaintext removal. Bundle tests reject the monitoring-only flag before producer execution; adapter cases bind staged credential paths, and a real systemd case converges ECH in a custom configuration directory without relying on a default key.
Controller path tests retain exact unit ownership and reject ambiguous or unsafe configuration selections before frontend credential reads.

ECH export and sentinel cases keep distinct nginx and ECH inner identities. The real native recipient matrix also retains that distinction, so hostname fallback cannot silently bind ECH to the unrelated frontend.

Parser adoption regressions execute both CI installation fragments with checksum-verified real sing-box bytes and an owned destination. Local acquisition supplies verified, tampered, truncated, wrong-version and incompatible-executable archives. Refusal must retain the prior inode and an actually usable parser; successful full-profile acceptance must atomically replace it and clean staging.

Guidance coverage exercises the workflow's actual Git collection against an advanced base branch. Preserve full history for three-dot comparisons; a shallow fetch can hide the merge base after checkout.

Baseline resource tests execute its real first Ansible assertion and require an invalid value to stop before the next mutating task. ECH native leak checks run Hysteria with debug logging as well as secure positive/negative recipient traffic. The systemd generation case adopts both BBR profiles under the actual credential sandbox.

The complete native transaction suite is split into two disjoint CI groups in independent fresh systemd containers; both are required and a collection test proves their complete union. Keep the full local Make target unchanged.
Each case imports installed runtime helpers only after its own lab has established the module path; isolated partitions must not depend on earlier cases initializing the interpreter.
ECH probe regressions exercise both isolated import and Ansible's inline loading. Whole-route snapshot cases retain private ECH bytes, permissions, group and exact absence; generation helper unit cases establish their own runtime library path.
ECH identity admission excludes literal IPs before executable acquisition. Native UDP listeners probe the UDP port space; BBR recipient tests retain the paired XHTTP intermediate while refusing unqualified engine output.

Warm Hysteria upgrades retain Salamander and exercise the canonical firewall redirect through the lab veth. Per-port counters must observe an actual five-second client hop before and after upgrade and compensation; a datagram outside the range remains unchanged.
The native client may randomly choose its current destination again. Keep authenticated traffic running within one finite observation deadline until counters prove two distinct destinations, then require a fresh authenticated request before accepting the hop.

ECH native traffic stays in a private netns. Host-wide UDP ceilings are observed, tuned and restored before entering that namespace because Linux 6.8 does not expose them there. Packet decoding explicitly selects QUIC for the allocated test port. Capture only supported-recipient traffic and trust failures, outside the throughput measurement interval. Root CI steps preserve the pinned Python PATH.
The controlled 0.1% random loss applies only to concurrent throughput measurements. Single-datagram UDP/DNS functional assertions retain the same five-millisecond path without injected loss, so expected UDP loss cannot randomly invalidate acceptance.

Native frontend fixtures verify the same upgraded Hysteria bytes as the builder. Smoke control-flow fixtures load the deployed CA directory from shared group variables; encrypted synthetic fixtures must track the plaintext runtime selection.

ECH unit cases check wire framing, private/public key agreement, identity/generation matching, strict emitter routing and root-only systemd credential wiring. They are source evidence; exact native ECH negotiation, packet identity, traffic and generation compensation have a separately selected Linux lane.

Runtime publisher tests verify retained directory descriptors remain valid
inside normal and predictive transactions and close after success, exceptions,
interrupts and failed entry or lock acquisition.

AWG device tests use real SOPS/age round trips for selected pool issuance,
revocation and interrupted/unsafe publication. The named native binding target
owns isolated namespaces and exact pinned AWG builds; it proves two devices'
TCP/UDP traffic, wrong keys/headers and selected revocation with the other
instance still working. Portable mocks never stand in for this runtime proof.
Atomic enrollment Bats cases run actual encrypted transactions too; their CI lane
installs the pinned Python environment and checksum-verified SOPS with age.
URI QR boundary tests consume actual encrypted issuance and inspect the exact
codec input; failure retains the private URI for recovery. Dash-prefixed device
names exercise both the shell wrapper and Make issuance/revocation surfaces.
Binding cases reject absent registry authority and cross-instance duplicate
devices. Shared encrypted/native fixtures contain complete matching recovery
keys and registry bindings for every device. Real encrypted Make defaults and AWG-only revoke/reissue cases preserve
non-AWG registry fields; schema tests share runtime interface-name boundaries.
FIFO sources must refuse promptly and release the writer lock. Make audit
regressions decrypt actual age envelopes and require no event for failed
transactions; first-time token entries must satisfy the complete secrets schema.
Multi-host refresh tests use distinct per-host documents and keys, retaining
explicit AWG delivery selection despite missing or conflicting ambient input.
Mutation tests preserve ciphertext when any unrelated registry relationship is
broken; de-onboarding rejects rebound provider/environment identities. Isolated
inventory fixtures copy the shared AWG registry module with the secrets validator.

XHTTP endpoint acceptance is a separate complete target within the native job.
Its cases and the existing native/RTA lanes form a disjoint complete collection,
with selected skips fatal. Both served ports exercise actual pinned clients,
conflicting forwarding headers, private backend peer observations, discovery,
complete native candidate refusal and Hysteria's owned TLS proxy. ARM64
native runs require the repository-pinned base and exact ARM64 runtime checksums;
emulated executable identities cannot stand in for native authority. Runtime
upgrade fixtures share one admitted path-free origin between canonical identity
and Hysteria input; a trailing slash is a path and refuses before acquisition.

Payload-classification fixtures control elapsed time independently of curl
completion. Uniform and spiking RTT scenarios execute the real classifier;
the clock shim delegates every other Python invocation to the pinned interpreter.

Destination fixture gateways claim both TCP and UDP sockets on the same native
gateway port before accepting a candidate. Cross-protocol address collisions
release both candidate sockets within a finite allocation bound; other errors
propagate. The regression creates a real conflicting UDP lease.

Native Hysteria validation checks root-private transient unit permissions before forced publisher death; portable recovery rejects even an exact recorded public-unit claim before touching the service or lease resources.

Sender queue regressions preserve the pinned atomic metadata and empty initial-chunk staging forms, reject invalid names/sizes, and bound live inode-change retries separately from foreign-authority refusal.

Sender activation regressions include the handler-flush boundary after a rescued first cutover. Adapter timer notifications require durable sender acceptance before unit installation.

The enabled collector scenario verifies 42,000 current, 24-hour historical and
churn samples from ten fixture node labels through the managed sender, including
exact values/timestamps after durable-queue restart and unchanged resource/public
nginx boundaries. It is a bounded cardinality workload, not ten enrolled hosts or
seven-day capacity. The Kuma CI role job also runs its pinned upstream image
with network disabled, verifying missing-signal timing, restart persistence and
age-encrypted isolated restore. External notification receipt remains unverified.

**Monitoring regressions cross the real boundary** — consume actual private
watchdog output, age frozen producer evidence with the pinned PromQL evaluator,
and compare declared units to partially missing native series. Long generated
alert URLs and realistic returned Message bodies exercise relay limits.
Grouped required-service failure and missing-evidence notifications retain each
unit's validated role through firing, recovery and exact omission accounting.
Observer termination tests execute the production backup/recovery helper;
fixture-only signal cleanup cannot prove the installed service's restoration behavior.
Pinned receiver readiness retries only expected startup HTTP 503 and refused or
timed-out loopback connections within one deadline; unexpected errors propagate.

Set fault-injection permissions explicitly when rejection depends on mode; restrictive CI umasks can otherwise create a safe node instead of the intended unsafe fixture.

Pytest module basenames must be unique across `tests/unit`, `scripts/tests` and
`vpnd/tests`: the full collection and shard-consistency checks import them together.

Runtime audit regressions cover guarded and unguarded Xray log rotation, exact
producer-owned metric files with foreign-owner, symlink, hardlink and ancestor
refusal, and named AWG observers including a failed secondary instance. Native
Linux cases clear both IPv6 neighbor caches before strict-firewall exchanges and
retire metrics written by a real service account. Portable checks do not replace
these native systemd and packet checks.
Local Ansible observer fixtures set `become: false` and isolate Ansible config.
Task slices after AWG normalization supply its names-only output explicitly;
the dedicated AWG test executes the actual normalization prerequisite.
Retirement owner-map tests execute the actual consumer role variable declarations
and stdin expression through Ansible; YAML mapping keys do not expand Jinja.
Collector authority rotation tests isolate Ansible settings and enable local
connection pipelining. Their subprocess budget covers the complete Ansible
transaction; production readiness deadlines and rollback assertions stay intact.
Cascade and deploy parity fixtures use the same isolated local connection policy;
their complete transaction budgets do not change explicit deadline tests.
Bounded command tests exercise real pipe backpressure and exited-child cleanup
without suppressing live-process or repeated signal permission failures.
Schema-client regressions use real owned children and local Docker command
adapters to test blocked input, partial-write integrity, one shared deadline,
client shutdown before removal and uncertain cleanup refusal. The timeout
fixture waits for client readiness before delivery; these tests do not contact
Docker or prove daemon or provider acceptance.

**Project audit regressions cover operator boundaries** — synthetic Git histories
isolate ambient Git configuration only in temporary repositories. SSH and runtime
release fixtures set their intended group explicitly. Runtime release fixtures
set the group on their owned temporary root before they create child directories.
Installer tests reject invalid checksums and provenance before execution.
Host-selection tests cross the actual CLI and
shell boundaries; token refresh, private locks and promotion tests exercise
rejection and concurrent callers. These checks do not establish live host,
provider, release or Linux systemd acceptance.

**Operator incident verbs run real Ansible guards** — `test_operator_verb_scope.py` derives each play head (hosts, serial, any_errors_fatal, pre_tasks) from the shipped playbook and runs it with real `ansible-playbook` against a local inventory for no limit, a node list, a one-host group and a one-host pattern, asserting the marker task never runs on refusal. It also checks rotation against an inventory `env` that differs from `ENV`, uses the real `make require-exact-node` recipe and `make -n` wiring, and compares the alias grammar of both the Make guard and the vpnd rotation builder (`vpnd.runner.ansible.rotate`) with the play guard's, which cannot be tested from `vpnd/tests` because mutation copies lack `ansible/`. It also covers hostile `ANSIBLE_LIMIT` spellings (the marker is never created and the text never appears in `make -n` output) and refusal of any other goal in the same invocation. Recording `ansible-playbook` and `ansible-inventory` stand-ins show that inherited `ANSIBLE_SKIP_TAGS` and `ANSIBLE_RUN_TAGS` are scrubbed and that verbs sharing an invocation run one at a time under `-j4`, and a recording `make` stand-in runs the four guarded blocks the runbooks print, under `bash` only like their fences: the per-node revocation sequence of `RUNBOOK-rotate.md` and `RUNBOOK-deploy.md` and the REALITY keypair and restic password sections of `RUNBOOK-rotate.md`. Each is a subshell whose EXIT trap runs `make clean`. The revocation cases assert that every node is rotated and verified, the visible stop messages, that one `e` assignment sets the environment of every call (the harness reruns the block as staging), that the sequence exits zero on success and with the failing step's own status otherwise (the cleanup does not mask it), and that SIGINT, SIGQUIT, SIGTERM and SIGHUP delivered during a rotation, whether to the subshell alone or to its whole process group as a terminal does, or SIGINT during decrypt, stop the loop with `make clean` still the last step and a non-zero status. The two deploy sections assert that cleanup runs last with the failing status for decrypt, deploy and verify failures and for signals delivered to the subshell during deploy, and that a failed decrypt never reaches deploy. All four blocks also run with a `make clean` that fails (exit 1 after a successful run, the failing step's own status after a failure) and with a second signal of each kind delivered to the whole process group while `make clean` runs after an interrupt, which must still complete. SIGKILL and power loss cannot run cleanup and are not simulated. This establishes source behaviour only, not live host selection or SSH reachability.

**Recovery clock tests isolate their time facade** — copy the adapter's time
interface before patching sleep or clocks. Subprocess polling keeps real time,
so candidate validation cannot advance synthetic worker timestamps.

**Transport boundary proof uses real protocol paths** — portable tests cover typed authority and socket contracts; disconnected Linux native tests use the pinned gateways, sealed libc/NSS, real REALITY/Vision and XHTTP TLS frontends, and Hysteria TCP/UDP. Kernel tests count forbidden endpoint contacts after earlier ACCEPT and DNAT, while public traffic remains positive. Active lifetime and quiet quarantine are measured once in the common helper lane. An owned TUN fixture does not establish vendor WARP registration or live acceptance.

Native fixture configuration is written to private `0600` candidates and atomically published; TUN contexts yield only after setup and namespace restoration succeed. Peer, initial and replacement TUNs, capture sockets and bounded packet workers have lexical ownership; worker teardown precedes descriptor closure on success and failure. Private TUN fixture configs start as `0600` before writing and receive the gateway group only after complete serialization.

**Temporary validation reporting uses actual localhost Ansible** — two runs
execute the owned candidate lifecycle and retain accepted config/helper/unit/TLS
bytes and metadata. Real Hysteria semantic refusal must clean up without
publication. Predictive check-mode changes and a genuine persistent change must
remain visible to the installed Molecule idempotence parser. The portable Xray
candidate uses its real Python semantic admission function; this reporting test
does not establish native parser, protocol, or TLS acceptance.

**Interrupted protected ingress runs through the production tasks** — `test_transport_site_transaction.py` splices the real detection, helper-admission, adoption and refusal tasks from `transport-ingress-begin.yml` into the localhost harness, replacing only the journal, `pending.json`, outer-helper, outer-state-directory and `outer.json` `stat` paths, the state directory's root-owner condition (retargeted at the test user) and the outer status command, and drives the real nginx publication helper. The shared transport-egress `helper-authority.yml` task runs verbatim except that its interpreter, state root, helper directory, ancestry walk and root-ownership checks are retargeted at the harness tree and the test user. The egress quiesce and rollback tasks are stubbed, and the event stubs set `check_mode: false` so a check-mode run that wrongly quiesced is logged; separately, the retargeted outer status command writes a `status-ran` marker if it ever executes. It proves compensation order for an open, closed and absent egress outer route, next-run convergence, check-mode refusal without mutation, a pending-only `pending.json` journal that refuses dry-run as `interrupted-nginx-publication` (not the protected-ingress category) and is recovered by one deploy, refusal of a symlinked, group-writable, hard-linked or writable-directory outer helper before it runs, categorical outer-status refusal and a retained malformed journal, which with an open outer route quiesces the candidates but never resumes the accepted generation. A missing outer helper adopts the journal with the route treated as closed only when its state directory is absent or a root-owned 0700 directory without `outer.json` (the harness covers an empty one and one holding the accepted receipt); a state directory holding `outer.json` (as a file, a dangling link or a directory), that is a symlink or not a directory, or that is unsafe (a foreign owner or a mode wider than private) refuses as `egress-outer-helper-missing` before adoption, with no status helper run, no compensation and the journal retained, and a contract assertion ties those paths to the runtime helper's own. The real egress quiesce and rollback behavior remains native and Molecule evidence.

**Protected frontend lifecycle has one owner** — rotation selects the canonical
Xray/Hysteria roles under staging and invokes their guarded activation once.
Changed units, configs and TLS authority retain validate/snapshot/rollback
ordering. Actual localhost publication plus handler flush cannot dispatch a
second frontend restart; native role scenarios retain final readiness proof.

Native normalizer recovery also retains live authenticated TCP and UDP controls when killing the process. Both accepted TCP tuples must enter TIME_WAIT before one immediate restart with the original readiness deadline; fresh public TCP/UDP and zero forbidden contacts remain required. Closed-probe recovery alone cannot establish listener rebinding under active traffic. UDP tuple quarantine and gateway generation reset retain their separate authority.

**Shared transport semantics use real boundaries** —
`test_transport_semantics.py` covers accepted inputs, typed malformed values,
ambiguous client-name refusal, routed versus device claims, key reuse, prefix
collisions, privacy and actual
localhost Ansible preflight in normal/check mode. `test_transport_semantics_native.py`
requires an isolated Linux root/TUN host, exact source-commit AWG ELF outputs,
pinned Xray with adjacent GeoIP and checksum-pinned Hysteria. It fails missing
prerequisites rather than skipping. Native synthetic credentials are valid
runtime keys/UUIDs; source placeholders cannot prove parser acceptance.


**Review regressions preserve first-use boundaries** — invalid CI configuration
publishes categorical results before deployment; blue-green waits for bootstrap
after pinning and refuses before recovery instructions when readiness fails.

**Disposable trust tests exercise real boundaries** — build and inspect a real
private ext4 seed and verify its SSH identity; the native lane mounts its loop
block device in a private mount namespace and runs the guest installer. The
native sentinel test starts a real pinned loopback SSH daemon, rejects an altered
pin and stops only its owned unit. These tests supplement orchestration and
mock-provider checks; they do not claim a provider deployment.


**Audit regressions use executable boundaries** — localhost Ansible tests exercise synthetic-key redaction, DNS and forwarding transitions, canonical Xray drift, and rollback validation/activation failures. Saved-plan tests replace the original after inspection and verify apply still uses the inspected private snapshot. These prove local behavior, not provider or guest acceptance. Construct time-sensitive lease inputs at test execution, so a long collection-to-execution delay cannot turn an overlong lease into a valid one.

**Subscription first check mode covers planned service boundaries** — evaluate
loaded, absent, unplanned and failed systemd discovery plus restart handlers.
Real role convergence and first-host dry-run remain separate acceptance gates.

**Packaged SSH ownership has positive and interruption coverage** — cloud-init
tests consume the exact password-disabled image fragment, verify idempotence,
reject altered content and unsafe files, restore it after validation failure,
and repeat after process death at its removal boundary.

**Bootstrap classification follows real producer boundaries** — inventory
  carries the Terraform build label separately from workspace identity.
  Regressions exercise named production selection, contradictory inventory,
  duplicate or missing guest markers, and the emitted private request contract.
  The permanent-workspace bootstrap regression runs the real inventory renderer
  with synthetic Terraform output, then consumes its INI through bootstrap's
  custom parser. Handwritten unquoted labels cannot cover that codec boundary.

**Bootstrap failure diagnostics exercise the real child process** — assert
that failed installer output reaches stderr, structured stdout stays empty,
and the ambient enrollment key never reaches the Ansible child or output.

**Recovery check mode covers services and timers separately** — evaluate the
role's guards with loaded units absent from service facts, planned and unplanned
missing units, and failed load-state discovery. These unit inputs supplement
real systemd and post-convergence staging checks.

**Coverage claims follow contracts** — `test_governance_counts.py` checks role
and template inventories plus hosted scenarios. Suite sizes come from runner
output for a specific revision; this test does not recollect the suite.

**Workspace discovery uses real Git histories** — `test_workspace_status.py`
exercises linked/detached worktrees, divergent and missing main refs, rename and
dirty counts with disabled/limited ambient rename detection, non-UTF-8 index paths,
quoted control characters, fsmonitor hook isolation and an unchanged index.
The sanitized Make entry bypasses inherited inputs and an invalid `.fleet.mk`;
task-pointer checks use the real `taskctl` portfolio API. A real blobless clone
with a recording upload-pack hook proves status cannot demand-fetch objects.
Active clean/process filters and child-submodule filters are refused before
execution; unused configured filters remain supported. Empty selected task IDs
fail instead of silently becoming an unspecified task.

**`ci-fast` is the portable pre-PR gate** — runs the credential-free required
CI checks, including workflow/YAML/shell lint, cloud-init schema, all Terraform
tests, pytest/bats, Go helper integration, and vpnd Python tests, lint/type
checks, baseline parity, packages and dependency policy. `make check` adds
Terraform fmt/validate, gitleaks, and ansible-lint. Native Linux runtime integration, Molecule, GitHub-native
security services, and credentialed deploy jobs remain CI-only or explicit.

**Snapshots, not mocks, for templates** — `tests/snapshot/golden/` holds
the expected output of every Jinja render against fixtures. Drift is
visible in PR diffs.

**Baseline parity outlives planning** — the vpnd transfer gate reads its
permanent package inventory. Test it without an active OpenSpec directory;
task archival must not remove executable regression obligations.
Role-render tests reuse `scripts/template_render.py` for named-template escaping
and Ansible filters. Local HTTPS fixtures explicitly require TLS 1.2 or newer.
HTML/XML names include their compound `.html.j2`/`.xml.j2` suffixes; markup
values escape, while embedded JSON remains parseable and script-safe. JSON,
shell, unit, nginx and explicitly named text fragments retain artifact quoting
and exact credential characters. Recovery conditions use the same environment
policy even though expression evaluation does not produce markup.

**Client configs need an upstream parser gate** — CI installs a sha256-pinned
official sing-box binary and checks the complete standard emitter output.
Shape-only assertions supplement this gate; they do not replace it.

**Xray CI consumers share one verified installer** — template and sentinel
validation use `.github/actions/install-xray`. Keep its version/archive hash
together and aligned with the example version. Verify before extracting or
executing; install the runtime and its bundled geodata together after its
version command succeeds. Template routing rules need the adjacent data files.

**Pytest groups use measured durations** — four `pytest-split` groups share a
committed Linux profile. Keep `pytest unit tests` as the required aggregate: it
checks identical collections/profiles, disjoint selections and full execution.
Refresh the profile from the verified artifact; local `test-unit` stays complete.
Give clock-dependent parameter values stable IDs so collection agrees across runners.

**Promotion proof covers aliased temp roots** — the controller's snapshots
must reach the evaluator through canonical private paths even when the OS
returns a symlinked temporary root.
Provider promotion tests include an instruction symlink and generated cache in
`terraform/shared`; they must be ignored while the required shared inputs stay
regular, pinned files. A non-default workspace test also checks that Terraform's
first directory setup cannot violate the private snapshot mode floor.
Public-listener verifier fixtures use literal source addresses or complete
named-set objects; a dangling `@set` reference is intentionally rejected.
Disposable de-onboarding tests also exercise a reissued cleanup manifest after
firewall promotion and reject a foreign server UUID before any local deletion.
Disposable de-onboarding fixtures use the current UpCloud schema-3 absence
receipt and reject an obsolete version before mutation. Its registry fixture
uses the installer's exact sorted JSON format.
Unbound-retirement fixtures must start with registered pre-destroy state and
then write different empty state. Exercise copied/inode-replaced authority,
unclaimed absence and post-destroy state replacement before SOPS publication.
Prepared-executor tests require a completed real client retirement transaction,
profile marker/configuration/context guards, assignment races and interrupted
stop/delete retry; fixture success remains source evidence only.
Exercise real SOPS retirement both with and without optional Snell collections;
an absent section is valid, while malformed or partial configured state refuses.

**Disposable observability acceptance is evidence-class strict** — focused
schema-2 tests cover co-hosted VPN capabilities, one collector, independent
Kuma placement, exact push-monitor bindings and rejection of old host classes.
PKI tests exercise real OpenSSL IP-SAN verification, scoped revocation and SOPS
encryption/decryption, including strict certificate-chain checks with explicit
key identifiers. Refresh the encrypted synthetic fixture whenever its plaintext
counterpart changes. Tests that isolate HOME need real SOPS on PATH, not a
version-manager shim whose trust state depends on the original home directory.
Real pinned Kuma runtime timing is separate from mocked
push or Telegram tests; no synthetic receipt proves human notification.
Sender replacement checks use the actual pinned vmagent parser and persistent
queue behavior. Clean and abrupt restart evidence must query pre-restart sample
timestamps at the collector; queue files, empty buffers and fresh samples alone
cannot pass. Byte/block drop counters are not interchangeable with sample counts.
Historical dedicated-host
selector tests prove staging-only enablement, disabled production, required
explicit secret scope, and mixed-scope refusal before Terraform or publication.
The old global boolean must fail, not become an implicit compatibility path.
Focused
unit tests keep the fixed staging row order, exact-host and private-file
boundaries, real one-hour critical reminder program, interruption restoration,
durable receipt reconciliation, human-observation gate, complete-set cleanup
plans, provider-specific absence and redacted terminal schemas separate. The
rollback tests distinguish retained last-known-good inputs from the active
candidate, and invalid-candidate credit requires an exact one-field mutation
plus the typed first role-guard failure; another Ansible failure is never
accepted. Typed-refusal capture tests enforce the fixed 64 KiB streaming cap,
redacted failure, deadline, and owned-process cleanup. Authenticated negative
ingestion probes require an explicit HTTP
status while only plaintext and missing-identity TLS probes accept transport
refusal. The
local input preparer is contract-locked to that row order and proves no-clobber
private roots, fail-closed draft approvals/bindings, schema-valid SOPS runtime
fragments, secure sticky-only writable ancestry, descriptor-bound refusal on
root substitution, and real OpenSSL certificate purposes without provider or
Telegram access. A
fixture executor or synthetic HTTP status is source evidence only; it never
marks a live Telegram or provider action complete.

**Molecule per role > monolithic test** — role-level scenarios catch
config drift inside a role. Full-stack catches order/handler interactions.
The two full-stack scenarios run on separate matrix runners with fail-fast
disabled; `required checks` requires both to succeed.
Tailnet role Molecule also asks the real `systemd-analyze` in a PID 1 container
to parse the complete recovery/SSH dependency graph and fails on diagnostics
even when `verify` returns zero. This is static graph evidence only: its inert
`tailscaled.service` fixture is not vendor-unit, activation, or reboot evidence.
Its native OpenSSH check hides `/run` in a private mount namespace, requires
the real `-T` runtime refusal, and compares complete cold `-G` policy with
the ordinary dump and warm `-T` output. Preparation must not create `/run/sshd`.

**CI Python tooling shares one cached setup** — `setup-ci-python` always checks
hash-pinned requirements, even on a pip cache hit. Galaxy consumers set the same
absolute `ANSIBLE_COLLECTIONS_PATH` as the action's isolated collection cache.
OS, architecture, Python and both requirements files determine its exact key.
The `python validators` job preserves seven checks behind one required context.
The native lane consumes this setup through `setup-disposable-ci`; cache
coverage follows that composite and includes its required Galaxy installation.

**CI selection follows complete consumers** — common Python/static checks always
run; costly PR lanes follow the selector's path graph. Docs are bundled into
Python vpnd. Keep Ansible scenarios together for cross-role inputs, and full CI for
main/manual/shared/unknown changes. The final gate requires every selected job
and permits only planned skips; adding a job must update the selector and tests.

**Cloud-init schema uses Ubuntu package sources only** — its installer selects
the runner's `ubuntu.sources` for both APT operations. An unrelated preinstalled
repository cannot block this gate. Missing Ubuntu sources and failed updates
remain fatal; package signatures and the real schema validator stay enforced.

Runtime acceptance has a separate canonical-role Linux lab. It uses exact checksum-pinned runtimes, generated dedicated client/TLS authority and an owned routed namespace canary. Credential mount propagation is established before creating namespace references, so parent bind mounts cannot hide those references at cleanup. Upgrade, retry, check mode, failure compensation and real process-death cases must retain actual authenticated traffic and fail selected skips. Portable inode/state tests complement that lab and never claim service or client acceptance. The operator runtime rollback case asserts the rolled-back `xray.service` unit text, the live `MainPID` executable and a published receipt that claims no `ripdpi-transport-*.service` node, then that a following ordinary converge with the newer pin restores `current`, the unit text and the `MainPID` executable to the upgraded release with the rolled-back release as `previous`; portable tests pin its candidate set, that no egress-owned gateway unit is a candidate and that planning, whether it succeeds or refuses an unverified release, leaves every runtime-tree and transaction-state inode, mode, owner, link count and content untouched. Because that converge now follows the rollback, native retirement starts from the re-converged receipt rather than the rollback receipt, so retiring a receipt produced directly by an operator rollback is no longer covered natively.

## What's done well

- **Cloud-init encoding crosses the real Terraform boundary** — scalar tests
  run Terraform templatefile and YAML parsing for ordinary, punctuation, multiline
  and Unicode inputs, then compare the fixed CI renderer's parsed result. Legacy
  XHTTP tests select legacy mode explicitly and verify the previous port disappears.
  Null bootstrap strings remain refused. Native serialization functions are
  explicitly registered in the exact executable-coverage assertion.

- **Provider identity tests retain real mock state** — native lifecycle tests
  include positive unchanged plans; the subprocess harness shares legacy/current
  state, asserts safe attachment forgetting and exact identity refusal, including
  first adoption. `make tf-test` runs that harness explicitly; no synthetic
  provider result is live resource or guest proof. Policy tests execute real
  Conftest, while operator gate tests cover private snapshot reuse and cleanup.

- **Skill decisions have held-out scenarios** — `tests/fixtures/skill-evaluation-cases.json` contains requests, observed-input facts and separate assessment criteria. Independent evaluation receives only requests/facts and the skills; integrity tests do not stand in for observed behavior or live evidence. Private intent preparation tests execute real local publication and Make expression boundaries using synthetic inputs, without opening credentials or contacting providers.

- **Provider example parity is checked** — every explicit staging/prod listener
  example includes the default nginx HTTP redirect, so a copied environment
  reaches the same fail-closed runtime contract as the provider roots.

- **Contract-named tests** — `test_xhttp_endpoint_contract.py` rejects old
  trailing-slash paths and origin disagreement; its native companion exercises
  the admitted endpoints rather than asserting renderer text alone.
- **`snapshot-update` is explicit** — never updates on assertion failure;
  requires an operator running `make snapshot-update` after an intentional
  template change. CI never auto-updates.
- **`shellcheck` in CI** — every `.sh` file. Warnings break the build.

**Native acceptance fixture authority** — Runtime acceptance tests use actual checksum-pinned clients, owned TLS peers and Linux systemd/network namespaces. Real SIGKILL tests run the publisher in a separate process and require authenticated positive forwarding after recovery. Canonical role fixtures keep only source inputs from the render fixture; computed runtime paths and numeric identity projections must not override real role discovery.

Read-only sender admission is also executed through actual Ansible argv/stdin templating. Sender queue regression tests perform real private-file copies and in-place restoration across interruption checkpoints and partial cleanup; they assert historical bytes, original root inode, no-follow authority, exact backup identities and fail-before-mutation admission. Service mocks are portable orchestration evidence only. The enabled native Molecule scenario requires the exact historical nonce and pre-cutover timestamp to reach the authenticated receiver after an actual rejected candidate.

## Pitfalls

- Ubuntu Molecule consumers use one immutable digest from the repository-owned,
  security-gated publication. Refresh every consumer and pin regression together;
  never waive fixable HIGH or CRITICAL image findings.

- **Selected skips fail required pytest lanes** — portable tests use
  `make test-unit` (both `tests/unit/` and `scripts/tests/`);
  `native_runtime` tests run separately with pinned
  Terraform/Alertmanager and UID/GID capabilities on a disposable Linux runner.
  Both use `--fail-on-skip`. Never run the full workstation suite as root.
- **Compiled helper coverage is real Go execution** — `ci-fast` includes
  `make test-probe-matrix-mtproto`; Python driver tests cannot replace it.

- **Release SBOM is the locked Python inventory** — CI and publication share
  `.github/actions/vpnd-sbom`, which stages `dist/sbom.json`. The deployment
  example emitter serves `make emit-sbom` and is not the vpnd release SBOM.

- **Mutation CI distinguishes findings from execution failure** — only exit
  0 (caught) and 2 (survivors reported) are successful runs. The runtime tests
  exercise actual workflow shell error propagation and disposable-copy cleanup;
  real mutmut baseline and mutation execution remain the acceptance gate.

- **Snapshot files are committed** — never gitignore `tests/snapshot/golden/`.
  PR diff is the review surface.
- **Molecule needs Docker** — CI runners and operator workstations vary.
  Failing-to-find-docker is a setup error, not a test failure; the harness
  surfaces it explicitly.
- **State-changing test calls precede assertions** — capture retirement or
  retry results first, then assert them so optimized Python cannot omit the call.
- **Recovery readiness observes periodic work** — exercise successful completion
  of the same invocation, failure, contention, timeout, and identity changes.
  Waiting never starts a replacement worker or accepts cached success.
  Exercise apply activation through the real baseline planner and adapter as
  well: observing a current worker must precede the fresh proof, and both
  phases consume one deadline. Fixtures are not native systemd acceptance.
- **Cold Tailnet recovery has one readiness budget** — cover `NoState` and
  `Starting` before owned logout and after it, exhaustion and late replies,
  invalid status, reinitialization during identity verification, foreign
  identity and strict non-recovery callers. A fake
  monotonic clock proves bounds; the actual vendor cold boot remains staging
  acceptance, independent of these domain tests.
- **`validate-secrets.py` runs against the **schema**, not your real
  secrets** — by design. Strict mode (`--strict`) loads `VPN_SECRETS_FILE`
  and is operator-only.
- **Don't snapshot the diff of binaries** — QR PNGs, restic repos, etc.
  Snapshot the inputs, render the binary fresh, hash-assert if needed.

- Legacy bootstrap kernel tests use a disposable root-owned directory under
  `/var/lib` and a private network namespace. Their service fixture does not
  establish PID1, identity, Tailnet, or live client acceptance.

- Sentinel onboarding tests cover standalone XHTTP, REALITY, Hysteria2, AWG-only
  and mixed format selection. An unsupported unused emitter refuses in the
  fixture; required emitter failures must precede remote writes. These tests
  are orchestration evidence, not live authentication.

Native P2 check-mode coverage executes the complete enabled agent role against
valid generated TLS authority in fresh and retained namespaces. It compares the
owned filesystem before/after and performs no runtime download or activation;
ordinary Molecule/native runtime acceptance remains separate. The private
receiver snapshot CLI regression restores every mutable authority file and the
prior service-state record without rewinding replay or incident state.

Release-publication fixtures must explicitly chmod directories to the tested
contract after mkdir: the shared build gate uses a restrictive umask, so
mkdir's requested 0755 alone cannot establish the helper's ownership boundary.
Task-source readers follow enabled task files and recursively inspect real
publication blocks; dispatcher files cannot prove mutation or activation order.

The shared Molecule transport canary serves HTTPS with an exact numeric SAN and
container-local trust. Full-stack watchdog validation keeps requiring HTTPS;
standalone rollback fixtures prepare canonical consumer recovery before `begin`.
Portable publisher and validation-lease tests use private user-owned temporary
ancestry; Linux `/tmp` is deliberately outside the production authority contract.
Numeric canary startup bypasses reverse DNS inside its disconnected namespace.
Complete consumer transactions run in a pinned fresh systemd container on a
separate native runner, retaining refusal of foreign runtime and firewall
authority from the runner host or other fixtures.

The native policy lifecycle fixture requires a root-owned executable parent
without group/world write permissions. A disposable runner may start with
0777, so the fixture saves the mode, establishes trusted ancestry and restores
it in cleanup. Production retirement validation keeps rejecting unsafe ancestry.

Alerting regressions cross operator payloads into the real relay parser and renderer, and match exact send receipts. Lost canary responses and interrupted receipt writes must leave freshness absent while the next attempted sequence advances. A pinned real Prometheus receiver checks reordered queue batches without relaxing historical sample assertions.
