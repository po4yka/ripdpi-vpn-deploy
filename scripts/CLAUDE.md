# scripts — operator entry points

## Design decisions

Device migration uses separate source/target SOPS authorities and an encrypted
intent before cross-document writes. Exact inventory, host pins, alternate
sources and endpoint fingerprints fence resume. Publisher CAS preserves every
active URL and expiry; registry identity includes the exact migration metadata.
Preparation precedes target convergence. Publication and readiness re-run
target verification and an expiring credential-free TLS route canary, then
re-read authority before accepting delivery. Old credentials remain until a
separate retirement action. Keep published, received and fresh path-tested
states distinct; official-client attestations are explicit operator evidence.
Blue-green retains the target environment selector after handover because
delivered bindings now refer to it. Never rename target tfvars into the source
selector or recommend unconditional target destruction after publication.
Pair inventory rendering uses an owned temporary output and retains unrelated
publisher/alternate rows and memberships after strict admission. A changed
global SSH authority or concurrent inventory edit refuses replacement. A
topology-wide observability generation must be rendered by its complete owner;
the pair wrapper refuses it before provisioning. Standalone migration consumes
the complete reviewed inventory without re-rendering it.

Fleet status resolves provider/environment selections through strict inventory
inspection, preserving Tailnet transport, public host identity and custom ports.
Its local watchdog verdict requires a recent completed result; neither a timer
nor a listening socket proves client-path connectivity. Rotation uses canonical
authenticated liveness for distinct survivors outside the current/completed
original targets. The versioned plan owns the survivor mapping. Private locked
journals bind the entire plan, synchronize in-flight before external execution,
and never automatically replay an uncertain outcome. Dry-run has no state writes.

The offline AWG sentinel installer binds the same correction into its existing
toolchain inputs and returns those public inputs to its provenance caller.
Liveness and real-VPS lane readers require that complete identity from the
fixed trusted installed helper. Old five-field manifests refuse qualification;
retain their directories for rollback rather than rewriting their receipts.
The verified vendor archive is extracted only in the private build workspace
and removed there before strict postimage verification.

Native AWG builders share the role's exact source correction and one native
build receipt helper. Source qualification, compiled binary digest and the
relative canonical alias must agree. All three builders execute real checksum
unit cases with a temporary Go overlay before building; the overlay adds no
untracked source input to the admitted tree.

Checkout discovery passes Git metadata input through a private temporary file.
Large NUL-delimited path lists can otherwise block both stdin and captured
output before the query timeout applies. Preserve UTF-8 surrogateescape bytes,
the empty-input EOF, the deadline and all active-content-filter refusals.

Strict full-device kill-switch certification refuses partial TUN capture
selectors, including route sets, interfaces, users, packages, namespaces and
MPTCP exclusions. Parser validity alone does not prove device traffic capture.
SOCKS Unicode names require a lossless codec round-trip; deviation forms refuse
and require an explicit ASCII A-label. Do not use casefold for this identity
check. Cascade TCP directions drain independently after FIN with bounded
buffers and idle time, while empty UDP payloads retain ordinary association
admission and tuple quarantine.

Certificate preflight verifies enabled profile authorities against the operator
trust store and server-auth purpose. Canonical per-host inputs retain Ansible
replacement order; standalone default-profile checks are labeled accordingly.
Supplied certificate chains provide intermediates, never trusted roots.

Hysteria export retains metadata for each endpoint. Official-client bandwidth
hints use the shared exact-rate conversion with reversed client directions and
positive whole-Mbps rounding; liveness requires the same hints and includes
them in the public generation digest. These are negotiated per-connection
values. RIPDPI does not currently apply them, so no server-wide cap is claimed.

The audited Bearer clients share authenticated_http.py and refuse every redirect.
Protocol notifications require an HTTPS origin without userinfo, path, query or
fragment. Local HTTP tests inject transport after origin admission; production
has no plaintext bypass. State backups expose final names only after completed
age encryption and uses no-replace publication to preserve timestamp collisions.
Hardware enrollment binds explicit serial/slot selectors through literal Make
inputs. Resume retains its identity, migration preserves each file's recipients,
and staged ciphertext shares the existing per-document writer lock. Grouped
policies require separate quorum-aware migration. Generation diagnostics stay
on the operator's private controlling terminal. Subscription issuance requires
the installed publisher-v1 readiness protocol before external publication. One
service-owned atomic envelope binds exact payload bytes and expiry under the
existing lock; a lost acknowledgement remains an uncertain external outcome.

Inventory publication removes CR and LF from wrapped base64 before it constructs
INI fields. Strict host selection still rejects split records. Renderer tests
cover both line endings and verify typed listener and observability data through
the strict parser.

Blue-green treats each Make phase as a separate ordered command with inherited
Make controls removed. Dry-run accepts only 0 or 1 and resolves before private
inputs. CI commands use the retained bootstrap session supervisor; keep private
stderr capture separate from machine-readable stdout and reclaim descendants
before teardown even when the command leader has already exited.

Terraform environment admission reserves `default` for the legacy `prod` mapping.
Blue-green admits both names before private inputs; distinct admitted names have
distinct state paths. Cohort creation and state backup/restore reject the alias too.

State encryption writes an owner-only pending file and publishes a complete
backup with an exclusive hard link. Timestamp collisions wait at most ten retries;
retention never sees an incomplete ciphertext. File sync precedes publication;
directory sync follows removal of the private staging name. A sync failure refuses
success and retention, while a complete published backup remains recoverable.
Cleanup registers before allocation and removes only this invocation's pending file.
`restore-tf-state.sh` selects the
exact environment, decrypts into a private sibling, validates Terraform v4 state
structure and replaces accepted state atomically. Failure removes only its own
candidate; stop concurrent Terraform operations before recovery.

Recovery dry-run output and both runbook paths require authenticated host pins,
installed recovery generation, Tailnet handoff, SSH ownership and all three private
deployment mappings before convergence. A restored root snapshot is not fresh
SSH or promotion proof. Keep dependent Make goals in separate invocations.

Canonical client payload materialization refuses nonempty Hysteria port ranges
for RIPDPI with `RIPDPI Hysteria port hopping requires a qualified client` before publication.
Official sing-box hopping remains supported; the XHTTP-only native Xray selection
ignores unselected Hysteria. Keep the other engine compatibility guards.

State backup retention and recovery match the complete UTC timestamp suffix
after the exact provider/environment prefix. A broad prefix glob also selects
hyphenated sibling environments and can delete or restore their state.

P0 recipient admission distinguishes sing-mux from Xray Mux.Cool; a valid JSON
document does not establish wire compatibility. REALITY shortIds compare as
decoded, zero-padded wire values, and mtg accepts only structured FakeTLS secrets.
Field-level refusals must keep private input out of diagnostics.

VLESS UUID uniqueness follows the pinned engine's parsed authentication bytes,
including its reserved routing bytes. Different strings cannot share that
identity. AWG reserves every instance server host address against all device
and routed peer prefixes before binding, export, enrollment or publication.

Certificate preflight requires DNS SAN authority and complete wildcard labels
before native hostname matching. Do not restore domain-name regular expressions,
CN fallback or partial wildcards. Use `verify -verify_hostname`: OpenSSL 3.0
`x509 -checkhost` can exit zero on mismatch. Keep expiry and public-key checks separate.

RIPDPI Hysteria delivery refuses port hopping until its actual consumer is
qualified. The official sing-box path retains hopping. Per-host Hysteria
extension entries follow every emitted tag, not only the first host.

The REALITY monitor supervisor handles INT, TERM, HUP and QUIT before launching any decrypting child. The shell creates its work directory using an explicit parent path; BSD mktemp -t can ignore TMPDIR. Parent-owned temporary authority is removed after session cleanup on cancellation. Bounded child stderr is forwarded separately from the JSON stdout protocol. The monitor requests SOPS JSON directly into its private owned file; the general decrypt cache retains its YAML contract.

Federation preserves dependency edges between receipt-validated cancelled records. A cancelled prerequisite still refuses every non-cancelled dependent and never makes a task ready.

Taskctl archive maintenance relocates only owned inline task links. Dropped records retain immutable close receipts: readers verify the exact link projection from the archive’s reachable terminal source, rejecting every other byte change, including newline conversion. Repeated archival preserves timestamps/spec state; partial document-write failures restore the original record.

A successful alternate retains usable transport delivery, while any non-ok endpoint variant makes the operator decision degraded; exact primary/alternate observations remain separate and do not create a rotation candidate by themselves.

Task-history merge lanes retain the shared first-parent boundary, including
closure commits made before a branch updates from main.

XHTTP delivery resolves both configured direct endpoints through
`transport_semantics.py`, retaining each hostname and port. Native Xray output
is P1-only: each loopback SOCKS inbound routes to one exact endpoint, and the
unmatched default is blackhole. Typed bounded-pool controls require v26.3.27;
RIPDPI export refuses tuning its importer drops. The explicit monitoring
intermediate can carry the native fields, and liveness retains variant-to-endpoint
identity plus exact mode/tuning in its public profile map.

The AWG source-candidate runner admits only a local Unix-socket Docker daemon,
copies an explicit public-file build context and removes only its own
container ID. After an uncertain startup it polls the preallocated name for
30 seconds, removes it once observed, and fails with an explicit unconfirmed
cleanup diagnostic if the daemon outcome remains unknown. It binds
BuildKit and runtime calls to the admitted local engine context. Public sources
arrive as exact-commit Git bundles fetched over GitHub SSH port 22; credentials
and the agent stay on the workstation. Every invocation revalidates current
lightweight/peeled annotated upstream refs before accepting cached bundles.
Runtime execution has no external network
or published ports; compilation belongs under the machine-wide build gate.

ECH and BBR recipient fields are materialized in the shared Python payload path used by both delivery and drift inspection. The internal XHTTP-only selection retains semantic admission and is refused by bundle export.

Bootstrap registers plaintext cleanup before creating an exclusive private temporary document; ECH refusal, encryption failure and signal exits remove only that invocation's staging file. Existing operator plaintext remains intact. RIPDPI bundle export rejects the internal `--xhttp-only` monitoring flag before invoking any producer or reading secrets.

ECH recipients and liveness derive their default TLS identity from the declared inner name, independently of the nginx frontend hostname. An explicit Hysteria server_name must agree through semantic admission.

BBR resource profiles, like ECH, target the qualified official sing-box recipient. Unqualified RIPDPI export refuses before output; paired XHTTP monitoring requests only its explicit Xray intermediate.

Release eligibility evaluates high/critical advisories against the exact selected version and repository-owned module ranges. Historical fixed ranges may clear; unknown modules, missing ranges or unsupported syntax keep promotion blocked.

Bound bandwidth scalar length before integer conversion, so oversized numeric inputs refuse categorically within the supported 1 Gbps policy.

Hysteria release acquisition and ECH generation share scripts/hysteria-runtimes.json. These deployment-only pins are outside the client-mirrored contract directory.

Generator acquisition rejects nonregular sources through a bounded nonblocking descriptor before bytes are trusted. ECH issuance uses the exact checksum-verified Hysteria generator and encrypted_client_document publication lock. Only public generation identity reaches stdout. The supported ECH recipient is official sing-box 1.14.3; RIPDPI bundle export refuses the profile until its real consumer is qualified. Liveness retains exact public ECH material and refuses a different or stripped generation.

Federation reads the peer's own committed `taskctl export --json` contract;
it never parses another project's portfolio through this project's schema.
The shared graph validator checks exact identity, revision, contract hash,
relations, progress and terminal provenance. Purged references are resolved
by the owning exporter's `--resolve-task` with native receipt/history checks.
An unassessed peer risk remains null; no task records or receipts are rewritten.
Peer failure diagnostics stay categorical and bounded.

AWG peer `allowed_ips` is a typed IPv4/IPv6 mapping. Issuance allocates both
host identities before publishing ciphertext; exhaustion in either pool leaves
the prior generation intact. Address allocation jumps claimed intervals, so an
IPv6 /64 is bounded by peer count. Standalone and bundle emission share instance
MTU resolution with liveness; runner settings carry `addresses` and `mtu` and
install both default routes in the owned namespace. Public uplink admission is
read-only, requires the selected IPv6 default route, and refuses RA ownership
that would expire after forwarding enables.

AWG device issuance, revocation, export and recovery bind provider/environment,
instance and device through `awg_device_binding.py`. Only the nonempty instance
list owns peers and server keys. `awg_client.py` allocates from the selected
subnet and shares the private stable `.new-client.lock` with Naive/retirement.
`encrypted_client_document.py` stages ciphertext, verifies the entire decrypted
result in memory and atomically publishes only after original authority checks.
AWG revocation clears only the selected peer and its AWG recovery fields.
Preflight and credential mutations share registry validation in
`awg_device_binding.py`, checking both registry-to-peer and device-peer-to-registry authority;
routed peers are exempt from the device registry. Existing-device resolution
always requires the persisted registry binding;
device names are unique across all instances, including explicit selection.
AWG-only reissuance accepts a valid null binding with empty recovery fields and
preserves non-AWG metadata; globally revoked entries and all-profile reissuance refuse.
AWG Make targets apply normal host defaults and unexport original inputs after
literal capture, preventing Make function expansion during environment export.
Host environments follow the lowercase, alphanumeric-leading registry grammar.
Make AWG operations append best-effort encrypted audit records only after a
successful transaction; audit status stays on stderr so stdout remains JSON.
Encrypted source, lock and candidate opens are
nonblocking before regular-file validation, so a FIFO cannot hold the writer lock.
Subscription delivery records `awg_delivery_host` independently of device
authority; refresh restores this selector, including automatic selection,
instead of inheriting ambient host overrides. Missing delivery state refuses
refresh and requires reissuance. De-onboarding deletion paths require the
verified cleanup provider/environment and exact persisted instance; rebinding
a client to another host cannot authorize deletion through the old receipt.
First-time subscription registry entries initialize a null AWG binding and
empty recovery fields; existing AWG authority survives delivery metadata updates.
Bundle multi-host selection requires `AWG_HOST` when more than one enabled host
can bind; `AWG_INSTANCE` selects within that host. Missing enabled bindings
refuse without emitting a partial payload. The bundle retains the address array and fingerprint algorithm;
its admitted device address pair and MTU bounds are stricter. RIPDPI bundles support AWG-only profiles through
the direct carrier document; the official sing-box format still requires a
supported proxy outbound. Private recipient output uses no-clobber `OUTPUT`
publication in an owner-only directory. URI issuance also requires a private
new output reserved before source mutation; transaction failure removes only
that owned artifact. Credential-bearing URIs never enter metadata stdout. URI QR generation reserves
its own private recipient file, reads the VLESS URI from that file, and retains
it if QR rendering fails after enrollment. AWG CLI callers put the device name
after `--`, so dash-prefixed identifiers cannot become options or audit-only
successes. A null AWG registry binding also requires absence of that device
from every instance peer collection.

CI selects both native integration and complete transport acceptance together.
Each has its own disposable runner; the consumer lab never adopts or removes
another fixture's runtime authority. The required job graph checks both results.

The canonical render fixture supplies watchdog AWG interface names from synthetic
instances. Snapshot rendering uses the same pure effective-instance resolver
and never loads real credentials. Unsupported I1-I5 policy fields and nonzero
S3/S4 role defaults refuse before normalization rather than being discarded.
The secrets coverage checker declares this names-only role fact explicitly;
the complete AWG secret instance objects remain outside the environment file.

Passive command collection retries transient nonblocking pipe backpressure
within its original deadline and input/output budgets. Readiness is not a promise
that the next read or write can complete; broken input pipes still refuse.

The disposable cloud-init schema client uses one deadline for nonblocking tar
delivery and child completion. Partial writes retain their offset. Timeout
cleanup attempts to stop and reap the owned client before container removal.
Confirmed cleanup requires successful client shutdown and removal. Uncertain
shutdown still permits a bounded removal attempt for the owned name, but always
returns status `125`. An earlier daemon request may still be in flight: failed
removal remains uncertain even when inspection reports absence.

Subscription refresh binds the requested client name to the unique token-prefix
registry match before credential emission or remote publication. Prefix-only
registry compatibility remains unchanged; an ambiguous match refuses.

Secret rotation and warm-spare approval writers retain a private descriptor lock
in their parent shell. `private-operator-lock.py` validates its owner, inode,
single-link file and directory authority before locking and hardening old owned
locks to `0600`. Watcher publication and promotion consumption share one stable
`promotion.lock`, held through orchestration; neither process deletes the lock.

Verification admission passes the exact limit to Ansible inventory resolution.
`require-vpn-selection.py` then requires a VPN member, including child groups,
so a known observer-only limit cannot produce an empty successful play.

`rotate-credentials`, `rollback-xray` and `rollback-config` are exact-node verbs:
Make captures `ANSIBLE_LIMIT` as literal data into the `EXACT_NODE_ALIAS`
environment variable, `require-exact-node` checks it against the play's alias
pattern, and `ANSIBLE_LIMIT` then expands to the shell reference
`$EXACT_NODE_ALIAS`, so no recipe, including the shared `require-inventory`,
interpolates the alias into shell code (`ENV`, `PROVIDER`, `SECRETS_FILE`,
`ROLLBACK_XRAY_VERSION`, `SKIP_PRECHECK` and `ANSIBLE_DIR` are still expanded as
Make and shell syntax; SCR-1792057680449496 tracks them). That reference is not
an alias: the verbs refuse to share an invocation with any other goal, run one
after another (`.NOTPARALLEL`) when they share one, and `ANSIBLE_LIMIT` is
unexported so no recipe receives it. They start `ansible-playbook` without inherited
`ANSIBLE_SKIP_TAGS` or `ANSIBLE_RUN_TAGS`, which could skip the `always`-tagged
guard. The play asserts the one selected alias through
`ansible/playbooks/tasks/exact-node.yml`; that binding, not the `ENV` check, is
why each run acts on one node, so revoking a client is complete only after one run
per node. Rotation separately refuses a host whose inventory `env` differs from
`ENV`. `docs/how-to/rotate.md` and `docs/how-to/deploy.md` print the revocation
sequence as a subshell that names the environment once (`e=prod`), installs a
`make clean` EXIT trap before `make decrypt` and turns INT, QUIT, TERM and HUP
into exits: the per-node rotate and verify loop runs only after a successful
`make decrypt`, because a failed decrypt leaves an older plaintext file in place
that the loop would then deploy, and `make clean` runs on every exit path a shell
can catch (success, failure or interruption, but not SIGKILL or power loss, after
which the operator runs it by hand). The EXIT trap ignores those four signals
while `make clean` runs, so a second one cannot cut the shred short. The subshell
exits with the failing step's status, which the cleanup does not mask, and with 1
when only `make clean` fails, as the cleanup blocks in `docs/tutorials/quickstart.md` leave
the block unsuccessful. The REALITY keypair and restic password sections of
`docs/how-to/rotate.md` print the same guard around their `decrypt`, `deploy` and
`verify` calls; `test_operator_verb_scope.py` runs all four blocks, including
interruption. The ordinary re-deploy recipe in `docs/how-to/deploy.md` splits
preflight and deploy around the operator's review: a failed or interrupted
preflight cleans up, a successful one keeps the plaintext for the deploy block,
and the deploy and journal-recovery blocks clean on every exit; the same test
file runs those three blocks.

The release installer verifies the exact repository and fully qualified signer
workflow before installation. Cloud-init acceptance checks the actual loopback
SSH banner before it accepts the configured listener.

Explicit diagnostic addresses scope burn, probing and ASN checks to the selected
host. ASN state is separate for each address, so an override cannot compare or
replace another host's previous observation.

Disposable CI generates distinct internal normalizer/gateway credentials for every enabled guarded path, validates them through effective profile admission and keeps them out of process diagnostics.

CI credential generation uses the served `SERVER_NAME` HTTPS origin for Hysteria masquerade. The watchdog keeps its separate exact canary endpoint, including its path; a probe URL is not a masquerade origin.

XHTTP path and HTTPS origin admission live in `transport_semantics.py`, shared
by controller preflight, secret validation, emission and liveness. Canonical
origins include nondefault ports and omit 443; bootstrap exposes `--xhttp-port`
and CI generation uses `XHTTP_PUBLIC_PORT`. Make captures the port literally
and passes it through a quoted environment field before validation, never as
interpolated shell syntax. The only evaluated profile expression
is the exact repository-owned served-origin expression; arbitrary Jinja and
private operator origins are never rewritten or normalized.

- `transport_private_authority.py` reads bounded private configuration and the observed systemd credential ACL contract. Its credential exception is restricted to the exact private per-unit directory on a read-only mount, with effective read authority only for root and the service UID; ordinary files remain owner-only. Install that companion beside normalizer and classifier consumers.

**Recipient metadata has a fixed exit authority** — `transport_egress_config.py` constructs private fixed listeners and literal-only native gateways from admitted credentials and actual service UIDs. `transport_egress_host_context.py` reads kernel addresses and effective SSH/recovery ownership; `transport_egress_kernel.py` owns an atomic nft table and private receipt. The final output guard runs after earlier ACCEPT and destination rewrites. Unknown late hooks, packet duplication, TC/XDP and flow offload refuse admission. Resolver inputs remain numeric and sealed; no recipient domain is forwarded to a gateway.

Private-port admission distinguishes retired kernel TCP records from live socket authority: only `TIME-WAIT` with an explicit zero inode, zero or absent UID and no process owners can pass without the expected service UID. Live TCP, every UDP socket, nonzero inodes, missing inode metadata and foreign UIDs still refuse. This permits guarded recovery after active controls close without granting a live socket to another actor.

Normalizer refusal replies are best-effort only after admission has already failed. A client disconnect while receiving the refusal does not suppress resource cleanup: the connection, backend control, concurrency slot and worker record are released in the same finalizer.

Normalizer TCP listeners enable `SO_REUSEADDR` before binding so a new guarded process can recover while prior accepted TCP controls remain in TIME_WAIT after a crash. This does not share an active listener: `SO_REUSEPORT` stays disabled. UDP sockets, exclusive tuple pools, continuous-quiet quarantine and paired gateway reset retain their existing behavior.

**Transport relationships share one validator** — `transport_semantics.py`
validates globally unique client names and explicit cohort membership, effective
AWG headers/bounds/interface,
canonical 32-byte keys and noncolliding device or explicitly routed prefixes,
and owned HTTPS proxy masquerade. CLI requests use bounded JSON on stdin;
diagnostics contain fixed field paths and categories, never values. Enrollment
checks before generation and before encrypted publication; emitters and liveness
use the same rules. Disabled transports are excluded by resolved profile intent.
A broad prefix requires `address_kind: routed` and cannot be emitted as a device.
Named cohorts load only through validated repository-owned technical slugs.

**Native semantic fixtures use pinned real inputs** —
`build-native-transport-semantics.sh` provisions exact-commit AWG source outputs
and checksum-verified Hysteria only in the isolated Linux amd64 fixture cache.
It uses pinned Go with two jobs, rejects tracked source drift and never installs
onto a live service path. The native lane verifies source commits, compiled ELF
outputs, actual parser/startup behavior and owned cleanup; fixtures and missing
prerequisites cannot become a native pass.

**Naive devices have independent encrypted identities** — `naive-client.py`
centralizes the three explicit Make verbs for issuance, revocation, and selected
credential readout. Selected readout requires an explicit new `0600` output in a
private `0700` directory, outside tracked source or under ignored `secrets/local/`.
Its stdout carries only metadata; linked/existing/shared output authority refuses.
It shares `.new-client.lock`, uses encrypted sibling publication,
refuses unsafe source authority, and preserves unrelated fields. Once ciphertext
replacement commits, a sync or descriptor-close failure reports
`committed-durability-uncertain` with exit 3 and retains the recipient artifact;
inspect the enrolled state before retrying. `new-client.sh`
includes optional Naive issuance inside its existing all-profile transaction.
No scalar credential compatibility path or plaintext staging is supported.

**Bootstrap issuance follows intrinsic retention** — the subscription resolver
uses role defaults, group/profile policy and encrypted overrides to create versioned
epoch-bound grants. Optional expiry only shortens the deadline, and its bounded
metadata is installed before the payload. No old-format bootstrap URLs are issued.

- SNI secrets are parsed structurally through PyYAML; only `xray.server_names` becomes probe targets, and malformed private input produces categorical diagnostics.

- Disposable CI creates its no-clobber public result directory before validating
  configuration. Invalid JSON, template selection and absent credentials produce
  categorical results without private inputs or starting provider operations.
- Disposable CI uses one private controller run per guest. A provider-imported,
  digest-bound SSH seed establishes first-contact trust; its private image and
  provider upload diagnostics never enter plaintext artifacts. Exact cleanup
  includes the seed, and seed-only cleanup never proves whole-provider absence.
- CI Tailnet policy is derived only from a confirmed handoff matching source,
  node, host-key pin and observed contexts in a typed CI cohort. Promotion uses
  the ordinary pinned Linux SSH sentinel at `ci-liveness` with actual activation
  metadata; the existing Colima executor retains its separate bound contract.
  Stop owned loopback/Tailnet units in every exit path on the ephemeral runner.
- The CI SSH sentinel creates OpenSSH's privilege-separation runtime before
  validation and retains PAM account/session checks with public-key-only
  authentication. Tighten an owned `.ssh` directory before publishing config;
  reject writable or foreign directories and report categorical stage errors.

**Blue-green stops for review** — apply follows the green plan and deploy
follows the green dry-run only after a typed `yes`. `promote-spare` reaches
the same prompts; its OTP authorizes the swap, not an unreviewed plan.
The blue-green, promote-spare and watch-spare recipes pass `BLUE_ENV` when it
is set, else `ENV`, and refuse an explicit `ENV` that names another environment.

**Blue-green authenticates before first contact** — verify the green public key through an authenticated channel and confirm its standard known_hosts entry before inventory rendering. Vultr secondary-IP discovery uses strict host-key checking; it never enrolls a new key. Wait for cloud-init through the pinned public path before presenting recovery-installation steps. Then establish Tailnet/recovery ownership, render the confirmed handoff, and let the canonical controller perform pinned readiness. Blue and green aliases must be exact VPN inventory members before verification or deployment.

**One secrets file, one environment** — the deploy controller refuses a
selection when `ENV` is empty or any selected host's inventory `env` differs
from it. The check runs before the decrypted secrets read, SSH and Ansible, so
an inventory with several environments never receives another one's secrets.

**Audit operator boundaries** — saved Terraform plans pass `check-tf-plan.sh` across all required policy namespaces; `policy-plan.sh` snapshots once, checks and applies that exact private file. Never replace it with a second plan. Reconverge, replacement and drift check-mode call the Make deployment controller. `diff-secrets.sh` uses the inventory transport and read-only Ansible comparison against the canonical Xray template; it never prints remote configuration or treats rendering failure as clean drift.

**Subsystem ownership and design notes live in [DESIGN-NOTES.md](DESIGN-NOTES.md)** — before
changing a listed subsystem, read its matching section:

| Before changing | Read |
|---|---|
| Task lifecycle (`tasks/taskctl.py`) | [Task lifecycle](DESIGN-NOTES.md#task-lifecycle--taskstaskctlpy) |
| Deploy controller and inventory rendering | [Deploy and inventory](DESIGN-NOTES.md#deploy-controller-and-inventory--deploy-controllerpy-deploy-source-identitysh-bootstrap_readinesspy-render-inventorysh) |
| Provider checks, `destroy.sh` and staging cleanup | [Provider lifecycle](DESIGN-NOTES.md#provider-control-plane-destroy-and-staging-cleanup--destroysh-check-vultr-control-planepy-ci-staging-) |
| Client emission (`emit-*.sh`) | [Client emission](DESIGN-NOTES.md#client-emission--emit-bundlesh-emit-singboxsh) |
| Passive inspection (`fleet-inspect.py`) | [Fleet inspection](DESIGN-NOTES.md#fleet-inspection--fleet-inspectpy) |
| Liveness sentinels, Snell refinement and real-VPS AWG evidence | [Liveness and retirement](DESIGN-NOTES.md#liveness-sentinels-disposable-staging-and-retirement) |
| Probe scripts (`probe-*.sh`) | [Probe scripts](DESIGN-NOTES.md#probe-scripts-probe-sh) |
| Probe matrix (`probe-matrix-driver.py`) | [Probe matrix](DESIGN-NOTES.md#probe-matrix--probe-matrix-driverpy) |
| Tailnet (`tailnet-*`) | [Tailnet](DESIGN-NOTES.md#tailnet--tailnet-) |
| Observability (`observability-operator.py`) | [Observability](DESIGN-NOTES.md#observability--observability-operatorpy) |
| Cloud-init acceptance harnesses | [Cloud-init acceptance](DESIGN-NOTES.md#cloud-init-acceptance--schema-fallback-and-cloud-final-restart-harness) |
| SSH recovery installation | [SSH recovery](DESIGN-NOTES.md#ssh-recovery--install-sshd-recoverypy-make-install-ssh-recovery) |

**Generated documentation mirrors its source** — `docs-reference.py` parses the
Makefile `help` recipe as text, builds the vpnd argparse tree without running a
command, and calls the `ai-docs` emitter into a temporary directory to produce
`docs/reference/make-targets.md`, `docs/reference/vpnd-commands.md` and
`docs/llms.txt`. `--check` compares and exits 1 on drift; `make docs-check`
runs it inside `make check`. It reads no credentials, inventory or secrets.
Change the help text or the parser and run `make docs-reference`; never edit
the generated pages.

**Checkout discovery precedes operator configuration** — `make workspace-status`
reports local Git metadata without parsing `.fleet.mk` or reading runtime inputs.
`scripts/workspace-status.py` describes the caller's checkout, including detached
HEAD, dirty counts and the known local `origin/main`; it never fetches or refreshes
the index. Git queries disable fsmonitor to prevent configured hooks or monitor
startup. Active content filters and tracked submodules are rejected before
status, because dirty detection can execute external commands there; disabling
filters would invent differences against normalized index blobs. Configured but
unused filters remain supported. Optional `--task` pointers come from the canonical
`taskctl show` API; explicitly empty selections fail. Task queries have a bounded
five-minute deadline for committed closure-history audits; ordinary Git metadata
calls retain their independent 30-second deadline. Failures expose only the
categorical discovery diagnostic, never captured task output.
The documented entry clears inherited Make inputs before Make starts; Git status
uses explicit unlimited rename detection and lossless path decoding; lazy object
fetching is disabled, so missing required blobs fail locally. Text paths are
JSON-quoted to preserve field boundaries.
Discovery accepts no Make command-line assignments. It identifies variables by
origin and rejects them without expanding values, including recipe controls such
as `SHELL` and `.SHELLFLAGS` that Make itself consumes.

**Shell + Python, no compiled binaries** — every script must be readable on
a fresh box without a build step. Most are bash; the rare ones with non-trivial
data shaping are Python and use only stdlib + pinned `PyYAML`, `Jinja2`, or
`certifi` from `requirements.txt`.

**One file per operator verb** — `bootstrap-secrets.sh`, `rotate-secrets.sh`,
`fleet-rotate.sh`. The Makefile wraps these with `make <target>` shorthand.
`observability-operator.py` now selects co-hosted VPN capabilities and the
independent typed Kuma observer; dedicated-host `bootstrap` refuses before
host access. Local `render` and syntax `validate` do not admit a host; `check`
requires explicit host-access confirmation. Private-IP PKI preparation produces
an encrypted fragment without contacting a host or issuing Telegram credentials.
The shared PKI helpers explicitly emit CA/leaf subject-key identifiers and leaf
authority-key identifiers; strict verification must not rely on OpenSSL's
implicit extension defaults.
`observability-staging-acceptance.py` retains the historical dedicated-host
staging contract, not acceptance for the current co-hosted topology: one
invocation advances one repository-defined live row from a private canonical
manifest, approval and journal. Keep the critical reminder at the real one-hour
interval, require separate human-observation booleans, restore interrupted rows
before later work, and emit only categorical private receipts. Never add a
caller-supplied command, unit, endpoint, environment or arbitrary fault.
The fixed sequence includes negative ingestion, bounded persistent-queue recovery,
missing/stale evidence, grouping/inhibition, finite-silence, sender and
Telegram old-material rejection, invalid-candidate refusal, valid activation,
and exact control-plane rollback rows. Old sender proof uses the retained
private generation only for a rejected TLS handshake; candidate generation and
TSDB identities remain private controller evidence and never enter receipts.
The retained `agent-wal` row identifier now exercises the current vmagent sender.
Read transport from the fixed service's stable MainPID and bounded argv, not
removed Prometheus remote-write YAML fields. Queue bytes, sent blocks and HTTP
or persistent-queue drops have distinct units; no counter substitutes for a
collector query proving the exact node's historical sample inside the outage.
Keep the staleness mutation journaled on the canary and held until the control
plane independently observes the firing alert; every exit restores the exact
producer timestamp and prior watchdog-timer state before later checks. Finite
silences use an approval-derived reason and the gateway's private authoritative
journal so normal and interrupted restore delete every silence created under
that exact owner, node, and approval authority. Transport/TLS failure is valid
rejection evidence only for the plaintext and missing-identity TLS probes;
authenticated path, method, query, and admin probes require an explicit
non-2xx HTTP response, and the authenticated positive write remains strict.
The invalid-candidate row first render-checks the complete candidate, then
accepts only the operator's exact pre-mutation control-plane role-guard refusal
for a full configuration with only `prometheus_listen` changed. Real and
interruption rollback always pass the digest-bound retained last-known-good
vars and secrets, never the active candidate inputs. Capture typed role-guard
output incrementally under the fixed 64 KiB cap and deadline; overflow or
timeout must kill the owned process group and expose only the categorical
failure.
`prepare-observability-staging.py` is the local-only authority and input
preparer for that fixed run. It requires a clean protected-main source and
private canonical configuration plus already-issued Telegram values, creates a
new task-private root without clobbering, retains SSH and age identities only
there, and encrypts generated PKI/runtime authorities directly to SOPS. It must
not contact provider or Telegram APIs, create bot/provider credentials, print
private paths or values, infer approval, or turn null binding/rollback drafts
into executable authority. Materialization is a separate explicit verb and
publishes only a same-owner mode-`0600` file under that root.
Every input/root ancestor is opened component-by-component without following
symlinks and must be owned by the current user or root; writable ancestors are
accepted only when sticky. Keep root, subdirectory, secret creation, and
materialized replacement bound to directory descriptors and verify the
canonical inode bindings before success. Do not regress this to path-based
check-then-open operations.
Telegram `topic_id` is `0` for direct/non-forum chats so runtime senders omit
`message_thread_id`; positive values are reserved for real forum topics.
`ssh-ownership.py` is the explicit fresh-node SSH ownership verb between
dual-path Tailnet bootstrap and ordinary deployment. Its private configuration
binds the exact source and one inventory alias; check mode only previews.
`staging-tailnet-recovery.py` is the disposable-only acceptance verb behind two
fixed Make targets. It deliberately kills the enrollment worker or reboots the
node after durable pending state; it never exposes a general fault selector or
adds a guest RPC. Reboot failures after observed SSH loss publish a separate
redacted private `incomplete` diagnostic; that artifact is never success
evidence and never emits the success audit record. Once SSH loss is observed,
its already validated path and parent inode stay frozen so a later wrapper
change cannot suppress the failure receipt. Wrapper schema 2 requires that
fresh diagnostic path; obsolete schema 1 refuses before SSH.

**SOPS gate everywhere** — anything that reads decrypted secrets refuses
without `VPN_SECRETS_FILE` or the Make-resolved `SECRETS_FILE` produced by
`make decrypt`. Never assume `/tmp`, and never re-implement decryption.

**Runtime bundle validation is a narrow SOPS exception** — a client-side
materialized bundle is not an Ansible secrets document. The explicit
`validate-bundle.py --runtime-materialized` mode may read it only as a
same-owner `0600` regular file through a symlink-free, owner-controlled path,
redacts the key in memory, and never rewrites or logs the artifact.

**Destroy confirms a parsed hostname** — `destroy.sh` reads only a quoted
`server_name` from the tfvars file and refuses before Terraform when there is
none. Its EXIT trap removes the ordinary saved destroy plan on every exit.

**Destructive scripts always audit** — they append to
`audit-log.sh append-best-effort` after a successful run; there is no
opt-out flag.

**Terraform is workspace-routed centrally** — scripts call `scripts/terraform-env.sh`, which maps `PROVIDER` + `ENV` to the correct local state workspace. `prod` intentionally selects Terraform's legacy `default` workspace; the environment alias `default` is refused. New environments must be initialized through `make ... init`.

**Provider roots share one inventory schema** — UpCloud, Hetzner, Vultr, and Scaleway export the same canonical outputs, so `render-inventory.sh` stays provider-neutral. Add provider-specific inventory code only when a control-plane address needs extra guest convergence proof, as Vultr's secondary IPv4 does.

**Inventory inputs fail before publication** — nonempty cohort slugs must name an existing `group_vars/vpn-*.yml` profile, and host aliases must be unique across provider/environment pairs. Reject malformed profiles before Terraform calls and preserve the last valid inventory on either failure.
Base64 listener and topology values remove both CR and LF wrapping before INI
publication; encoders on supported operator hosts can emit either line ending.
Observability enablement comes from the tracked `enabled_environments` list and
the selected provider/environment pairs, not ambient `ENV`. Reject mixed
enabled/disabled scope before Terraform. Strict secret validation requires
explicit `--environment` arguments; host controllers derive them from immutable
inventory metadata. The old global boolean is not accepted.

**Tailnet inventory transport is confirmed** — `TAILNET_HANDOFFS` accepts one
private mode-0600 bootstrap handoff path or `-` per selected Terraform host.
The renderer validates the complete path list before Terraform calls, then
binds each handoff to the Terraform alias, public address, SSH port,
confirmation digest and actually proven Tailnet address family before changing
only `ansible_host`; the
Terraform public service address and listener contract remain authoritative.
The public-listener verifier reads the complete nftables `inet filter` table:
Tailnet SSH source matches refer to named sets, so their live members and
address-family types must be checked alongside the input-chain rules. ICMP
accepts require an explicit type match; a protocol-only accept is broad.
`fleet_inspection.select_hosts` uses `vpn_service_address` as the public
identity and `ansible_host` as the transport; a distinct Tailnet transport
must retain the public host-key alias for dual-path SSH proof.

**Liveness formats are selected by required profiles** — standalone XHTTP uses
RIPDPI emission and Xray; REALITY and Hysteria2 use sing-box emission. See the
liveness section of [DESIGN-NOTES.md](DESIGN-NOTES.md#liveness-sentinels-disposable-staging-and-retirement).

**AWG liveness DNS follows the role profile** — the private sentinel runtime
includes the role's validated IPv4 DNS servers. The runner writes a private
`/etc/netns/<generated-name>/resolv.conf` before the real hostname probe and
removes it with the namespace. Never use a fixed `curl --resolve` address as
proof of tunneled DNS.

**Promotion proof snapshots use canonical temporary paths** — macOS may give
`TemporaryDirectory` a path beneath symlinked `/var`. Resolve the controller's
new private directory before passing its executor snapshots to the evaluator;
the evaluator still rejects symlinked private input paths.

**SSH baseline failures have private categorical receipts** — deploy requires
an exact-alias mode-`0600` mapping to fresh absent outputs in owner-controlled
mode-`0700` directories. The deploy controller validates and freezes those
paths and parent device/inode before readiness, rechecks every selected sink
in one all-host preflight before the first SSH, and passes it to the baseline
controller for another identity check before publication. Unencodable surrogate
pathnames refuse before SSH.
Same-directory output names are case-folded and
Unicode-normalized so case-only and canonically equivalent variants refuse on
every operator filesystem. The baseline controller validates the sink before
the rest of the deploy request without coupling that authority check to
unrelated request fields. A malformed prepare receipt attempts bounded
rollback when its generation and nonce remain usable; otherwise it publishes
the categorically uncertain result. A deploy prepare RPC that returns no
receipt is also categorically uncertain because durable guest state may already
be armed; it cannot attempt rollback without the capability. Check-mode preview
retains its non-mutating RPC category. Publication occurs only after that
rollback or a handled interrupt has rolled back. Its CLI preserves a
nonzero interrupt status but emits only the generic public error. It publishes
only its allowlisted failure category with no-follow, no-clobber and fsync.
Keep the Ansible task
`no_log`; success and check mode leave the output absent. A missing receipt
after abnormal controller death or publication failure is an unknown outcome,
not success, and receipts never satisfy promotion or protocol proof.
Disposable liveness de-onboarding after provider firewall promotion supplies
both the original binding manifest and its reissued cleanup manifest. Their
private hashes, immutable resource identity, account, deadline and state path
must match the verified provider absence receipt before local removal.

**Provider promotion snapshots only Terraform inputs** — pin the two referenced
`terraform/shared` files explicitly. A recursive shared-directory copy would
include the `AGENTS.md` instruction symlink and generated Python cache, causing
promotion to refuse before planning. Required input files still fail closed if
missing, symlinked, or unsafe. Pre-create the selected non-default workspace
directories inside the private snapshot so Terraform cannot add `0755`
directories during its first command.

**Disposable de-onboarding consumes current guarded UpCloud absence** — its
provider receipt is schema 3; keep the provider and version check aligned
before removing encrypted client state or the executor profile.
The sentinel registry uses the installer's sorted JSON serialization, which
the de-onboarding reader must preserve exactly during removal.
Unbound recovery also requires the registered manifest inode and reserved
verified-absence path; pre-destroy and genuinely empty post-destroy state
hashes differ. Freeze the latter digest/inode throughout client retirement.
The separate prepared-executor verb requires the completed client receipt and
unchanged final ciphertext, serializes profile ownership against binding, and
retains removal intent for stopped/absent retry. Never fabricate a binding to
remove a prepared VM or reuse a retired one-shot profile name.
Snell is optional in issuance and unbound retirement. An absent section has no
client edges; configured variants must still contain exactly one issued client.

**Xray migrations are changelog-driven** — `docs/reference/xray-release-line.md` embeds the declarative guard registry consumed by `check-xray-breaking-changes.py`. Add version-aware rules there instead of hardcoding release cases in unrelated validators; render-sensitive rules use `template_render.py` so every fast check sees the same canonical Ansible context.

**Observability staging cleanup is an aggregate all-provider transaction** —
`observability-staging-cleanup.py` is fixed to the exact `staging` UpCloud,
Hetzner, and Scaleway tuple. Its snapshot derives identities from routed local
Terraform state, `seal` binds the separately supplied destructive-data
approval, and `run` validates every account, state, resource and reviewed
delete-only plan before the first apply. It emits a redacted receipt only after
provider-authenticated absence; never turn it into a generic provider,
environment, URL, address, or command runner.

**Python CLI delivery is verified before publication** — build-vpnd-package.py
copies reviewed tracked Python sources and Markdown, rejects source symlinks,
and generates canonical parser-derived manuals. check-vpnd-package.py compares
reproducible artifacts and checks isolated offline installation, packaged assets
and upgrade recovery. install-vpnd.py validates the native bundle, exact locked
wheel closure and private publication transaction before changing the launcher.
Dependency policy verifies pinned wheel hashes, reviewed SPDX license text and
non-yanked official registry metadata; it complements the vulnerability audit.
The parity gate reads the permanent `vpnd/test-inventory.md` baseline, so
archiving a planning change never removes its test obligations.

## What's done well

- **Promotion-intent preparation is local** — `prepare-disposable-promotion-intent.py` consumes literal environment inputs through an isolated Make target, reads one private JSON configuration and uses the existing disposable validator. It publishes a no-clobber private intent plus exact-alias mapping, keeps credentials unopened and reports no remote success. Retained partial output is not a completed mapping; runtime readiness and authority remain controller checks.

Staging cleanup has one private controller journal per provider/account/server
UUID. Keep publication/reissue and receipt operations under its shared lock;
`destroy.sh` inherits that lock through Terraform. Alternative artifact paths
must never create a second reservation or recover an active controller. Reissue
binds the previous generation, original state path and unchanged deadlines.
An exact retry of a committed publication is acknowledged only when the journal's
prior generation matches the retried request.
Independent controller homes are not a supported shared-ownership mechanism.

- **`set -euo pipefail` everywhere** — fail-loud is the default.
- **`shellcheck` in CI** — the `ci.yml` workflow runs shellcheck on every
  `.sh` file; warnings break the build.
- **Idempotent where it matters** — `validate-target`, `check-certs`,
  `audit-permissions` can run repeatedly with no side effects.
- **One script = one job** — no flag-driven multi-mode scripts. `new-client.sh`
  and `new-cohort.sh` are separate even though they share boilerplate.
- **RealiTLScanner cache is launch-validated** — macOS builds use an isolated
  `GOBIN`, verify `-h`, and atomically replace the pinned cache only after a
  successful build. An executable bit alone does not prove the cached binary
  matches the host architecture or is complete.

## Pitfalls

- Ubuntu Molecule consumers use one immutable digest from the repository-owned,
  security-gated publication. Refresh every consumer and pin regression together;
  never waive fixable HIGH or CRITICAL image findings.

- **Cloud-init CI bindings are fixed** — render-cloud-init-ci.py encodes the
  shared template's scalar expressions for synthetic fixtures and refuses unknown
  expressions. Real Terraform serialization tests prove parsed parity; keep both
  renderers aligned when changing template expressions.

- **Saved-plan policy precedes operator apply** — `policy-plan.sh`
  privately copies the regular environment plan, uses the canonical workspace
  router for show/apply, and evaluates that same copy through
  `check-tf-plan.sh` and its single `terraform-plan-policy.py` evaluator. Temporary binary/JSON files are private and cleaned
  on exit. Evaluator failures, malformed results and zero policy checks refuse
  apply; diagnostics identify policy namespaces without printing plan content.

- Bootstrap lifecycle is bound to both the routed workspace and the canonical
  `vpn_build_environment`, then checked against the root-owned cloud-init
  marker. Named production workspaces retain their identity; disposable
  workspaces always require cleanup authority even with a production label.
  The renderer emits that label as a shell-quoted JSON string for Ansible's
  typed INI parser. `fleet_inspection` preserves the JSON text; bootstrap must
  decode it once before comparison, rather than comparing its literal quotes.

- **Bootstrap installer failures retain bounded Ansible diagnostics.** The
  sanitized child receives no enrollment key and retains no_log on sensitive
  status tasks. Capture at most 1 MiB and publish failed-play context only on
  stderr; keep structured controller stdout unchanged.

- **Bootstrap transport is node-scoped, never global extra vars.** Ansible
  extra vars override `delegate_to: localhost` too, redirecting controller
  validation to the VPS. Keep pinned connection settings in the private
  one-node inventory group and exercise real Ansible delegation in tests.

- **Normal bootstrap cancellation is not controller-loss evidence.** Its
  exception path requests rollback. Recovery acceptance must use the fixed
  staging-only harness, keep its child bound to parent liveness, observe exact
  worker `SIGKILL`, and accept only fresh timer or current-boot recovery unit
  results plus public SSH/SFTP and idle state. Recovery evidence must not reuse
  the positive handoff path, and a successful run must append its categorical
  best-effort audit record. Never add a caller-selected fault mode to the
  production bootstrap. After the destructive fault, retry only bounded,
  explicitly typed `SshTransportError` failures with fresh frozen inputs;
  cloud-init, semantic remote/recovery, source, unit and state refusals remain
  immediate failures. Reboot readiness
  belongs inside that post-fault retry boundary and must never issue a second
  reboot. Exhausting those transport retries publishes no success evidence.

- **Mutation builds require sibling inputs** — `test-vpnd-mutants.sh` copies
  tracked working-tree files before running Python mutmut in that owned
  temporary tree. Never mutate the operator checkout or suppress its exit code.
  Completed killed and timeout outcomes are detected mutations; survivors
  remain exit 2. Empty, partial, unexecuted or technically failed runs stay red.

- **SOPS snapshot filenames preserve YAML format** — disposable onboarding
  copies encrypted YAML to a `.yaml` snapshot because the canonical decrypt
  command infers its store from the filename. Keep the real SOPS round-trip
  regression; a mocked decrypt cannot detect this boundary.

- **Plugin path environment variables are not a complete isolation boundary** —
  Ansible also auto-discovers plugin subdirectories at playbook and role bases.
  Reject unsupported discovery/shadow-role paths before SSH; private cwd and
  disabled host_group_vars alone do not prevent a legacy vars plugin executing.

- **SSH connection timeout is not a session deadline** — bootstrap waits bound
  each SSH process group locally and each remote status query with GNU timeout.
  Remote deadline retries are distinct from an unresponsive SSH session; cloud-init
  exit codes 1 and 2 both refuse readiness even when the marker already exists.
  Keep raw cloud-init output suppressed and reclaim the owned SSH group on interruption.
  A private session supervisor reports command status without exiting. Keep it
  unreaped until group cleanup, so the group identity cannot be recycled. Command
  descendants inherit neither control nor status descriptors. Signal refusal
  remains categorical failure; control-channel EOF and unexpected status-channel
  errors independently reclaim the group. Bounded fallback wait or signal failure
  must retain the categorical cleanup error without exposing supervisor argv.
- **First-boot SSH uses only its selected key** — the wait adapter must ignore
  operator SSH config with `-F /dev/null`, disable the agent with
  `IdentityAgent=none`, and pass `IdentitiesOnly=yes` with its `-i` key.
  Otherwise unrelated configured or agent keys may exhaust server auth attempts.
- **Staging observability leaf certificates carry their CA key ID** — OpenSSL 4
  strict verification rejects a CA-issued client certificate without an
  Authority Key Identifier. Keep it in the generated leaf extension file.
- **Rollback state must be readable before mutation** — enforce the same byte
  limit on serialized pending writes and reads, including base64 snapshots.
  SSH/job/monitor deadlines must leave room around the shared probe budget.
- **Tailnet boot recovery cannot depend on sshd runtime** — `ssh.service`
  creates `/run/sshd` after recovery. Inspect the complete effective policy
  with syntax-validating `sshd -G`; `-T` also tests daemon runtime and can
  refuse a valid configuration before SSH starts. Keep full policy comparison.
- **tailscaled readiness precedes backend readiness** — recovery alone waits
  for `NoState`/`Starting` within one 30-second monotonic budget shared with
  the identity query and post-logout status check. Poll every recovery status
  observation and bound each query by the remaining budget;
  malformed, unknown and authorization states refuse immediately. Never relax
  identity ownership or the SSH recovery dependency to repair a cold boot.
- **Shell-injection on operator-supplied input** — any script taking a host
  name, client name, or path uses `"$1"` quoting and `printf '%q'` when
  forwarding to nested shells. Never `eval`.
- **Encrypted retirement receipts are phase-bound** — a terminal receipt beside
  a prepared or candidate journal is foreign state and must refuse before the
  SOPS candidate is created or published. Reject orphan candidate siblings;
  do not infer recovery from ciphertext content without the exact journaled
  inode and before/after digests.
- **`mktemp` differs on macOS vs Linux** — operator workstations are both.
  When a controller owns cleanup, use an explicit template under its `TMPDIR`:
  macOS `mktemp -t` prefers the Darwin user temp directory over `TMPDIR`.
  Private precheck copies must remain inside controller cleanup even when a
  timeout or cancellation kills a child before its shell EXIT trap can run.
- **`age` keyring location** — `~/.config/sops/age/keys.txt` on Linux,
  `~/Library/Application Support/sops/age/keys.txt` on macOS. The wrapper
  scripts pick correctly via `${SOPS_AGE_KEY_FILE:-…}`; don't hard-code.
- **`audit-log.sh` failures must not break the parent script** — use
  `append-best-effort` (logs the error, exits 0) rather than `append`.
- **Python scripts must run under the venv-less system python3** — operator
  workstations don't all have uv/poetry. Use stdlib + the pinned deps in
  `requirements.in`. Don't import `requests` (use `urllib.request`).
- **Never run raw Terraform from an operator script** — it silently uses the active workspace. Set `PROVIDER` and `ENV` on `terraform-env.sh` instead.
- **Galaxy drift lookups read only their temp install** — `ansible-galaxy collection list --collections-path <tmp>` also reports the configured default paths such as `~/.ansible/collections`, listed first. `check-ansible-galaxy-updates.py` must select the entry keyed by the resolved temp `ansible_collections` dir (macOS `/tmp` is a symlink); taking the first match reports an operator's stale local copy as latest and passes outdated pins. CI runners have no default collections, so only the manual review on operator machines exposes a regression.
- **Active REALITY target monitoring is filtered-vantage only.** `monitor-reality-target.sh` rejects an absent or `unfiltered` vantage, resolves the active target through the canonical secrets gate, and persists only a target fingerprint plus technical IP/ASN/prefix observations. It requires two consecutive unhealthy runs before notifying and never edits SOPS or invokes deployment actions.
  Match captured TLS markers in the shell: an early pipeline reader can SIGPIPE
  a still-writing producer under `pipefail`, falsely reporting a healthy path as blocked.
- **Burn-check textfile state is fail-loud** — `burn-check.sh` rewrites its
  Prometheus textfile from an EXIT trap. An external API failure removes stale
  reachability series and raises API-error plus incomplete-run gauges; a
  completed reachability failure keeps those gauges clear because it is a
  valid burn verdict, not a probe execution error.

- Existing-node bootstrap has three operator verbs: console rendering, read-only
  policy inspection, and enrollment. The RAM revoker and firewall replacement
  share a coordination lock; durable rollback always uses bridge-free policy.
  A reviewed legacy digest is not permission to adopt unexplained runtime drift.

- Tailnet firewall foundations flush rules atomically while preserving dynamic
  timed enforcement sets. Only the two exact static SSH source sets are replaced
  before the transaction-owned include, so removed approvals cannot survive.

`build-native-naive-test.sh` supplies the exact composite used by native tests,
with repository-pinned Go and a separate scoped GOBIN/GOPATH/cache. It never
substitutes stock Caddy. Local compilation uses the machine build gate; CI
keeps compilation at two workers and passes the verified output explicitly.

Operator alert drills bind the verified controller source and a unique technical policy nonce. They wait for an authenticated relay API receipt for that exact nonce and start time before resolution; submission and receiver selection alone cannot prove delivery. Human receipt remains separate.

Client delivery/drift changes must preserve the in-memory renderer and private
HMAC authority lifecycle described in [Private client delivery identity](DESIGN-NOTES.md#private-client-delivery-identity).
Issuance verifies staged ciphertext before remote publication under the shared
lock. Local SOPS and remote delivery are separate systems: after interruption
or a post-publication failure, reconcile the delivered artifact before retrying.
The callback marks external publication before the first mutating SSH attempt,
since a failed reply can follow a completed write. Subsequent failures or
interruptions return a reconciliation warning, including failed local replacement.
Validation-only callbacks leave that marker unset.

The encrypted client transaction runs its verified publication callback under
the stable lock even when plaintext registry state is unchanged. Same-second
refresh must redeliver without manufacturing an encrypted state change.

Profile and subscription dispatchers put the selected device after `--` while
retaining the client-first shell interface. Leading-dash device names stay
literal data through Python argument parsing; Make drift uses the same delimiter.

Enabled transport authority must contain nonempty typed credentials and SNI
before publication. Malformed consumed authority returns a categorical refusal;
missing optional QR tooling retains the committed delivery and machine-token
mode keeps its early exit without QR side effects.

The private identity binds the full enrolled AWG peer public key as well as its
instance. A coherent peer/recovery-key rotation can leave placeholder-based
exported JSON unchanged; it must still report stale without publishing key metadata.
Both typed device addresses and the resolved MTU are consumed payload inputs.
The coordinated dual-stack contract, exporter and runtime forwarding must land
together; the shared renderer must not keep a single-address or fixed-MTU path.

An explicit per-host cohort bypasses inventory hostname lookup: endpoint-only
AWG callers do not consume a hostname and must retain their export path.

Native acceptance fixtures cross unit and integration directories. Keep the
selector's native group closed over every consuming job, including changes
under `tests/native/`; a Python-only selection can omit real-engine acceptance.

REALITY validation shares `reality_target_validation.py` across point-in-time and
recurring callers. It normalizes comma/whitespace names once, verifies each SNI
through a trusted TLS 1.3 handshake with SAN-only hostname matching and H2 ALPN,
and forces HTTP to the same resolved address. Blocking DNS, TLS, HTTP, metadata,
and secret acquisition use the retained-session supervisor in
`bootstrap_readiness.py`; per-stage and aggregate budgets include all pairs.
Reports contain categories and counts, never target names or tool diagnostics.
Owned self-steal probes require an explicit service endpoint and exact owned SNI;
remote probes reject loopback endpoints. Ordinary HTTP is hygiene only. Optional
curl-impersonate 0.6.1 Chrome116 compatibility requires exact binary and profile
hashes and an actual handshake; it never establishes filtered survival or grants
promotion authority. No validator installs a client, edits secrets or deploys.

Task deletion audits compare against the explicit trusted base while retaining
feature first-parent lifecycle history. Importing a purge already in that base
is not a new deletion when no issue, execution or receipt changed outside it.
Independent lifecycle edits and merge-only resurrection retain the full audit.

The monitor wraps the canonical REALITY collector in one owned process session and parent-owned temporary directory. Invalid explicit target, name, mode and owned-public prerequisites refuse before missing private defaults are loaded.
