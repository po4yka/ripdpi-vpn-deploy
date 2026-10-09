---
task_id: ANS-1791562764586678
change: ansible-role-p2-remediation
commit_sha: 50fdff3f4f182783893155918dfd26f2b911b089
local: passed
local_evidence: Complete build-gated make check passed; 5702 portable tests, 22 subtests, 56 shell tests and 205 Rust tests passed; production lint, schema, policy and 150 snapshots pass. Scoped native runtime checks also pass.
remote_ci: required
remote_ci_evidence: Source 50fdff3f canonical AOP and transport jobs pass; native 82 of 83 pass. Corrected DNS/WARP/firewall fixtures and bounded baseline/CDN/authority diagnostics require a fresh hosted run.
dry_run: not_applicable
dry_run_evidence: Source-only remediation; no real inventory or SSH controller transaction.
staging: not_applicable
staging_evidence: No provider resources or live host rollout are part of this PR.
live: not_applicable
live_evidence: Production convergence and private-state retirement require separate scope.
client: not_applicable
client_evidence: Native local namespace and protocol fixtures are not external client acceptance.
artifact: passed
artifact_evidence: Independent host and transport reviewers approve the P2 source; existing PR 282 contains the published extension and scoped evidence.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-P2-ACCESS | ANS-1791563231017425 | TLS/SSH authority, actual predictive Tailnet and mandatory sysctl boundaries | passed locally |
| REQ-P2-ENFORCEMENT | ANS-1791563231017425 | Effective APT/jail, nft failure and timed dynamic-set preservation | passed locally |
| REQ-P2-PUBLICATION | ANS-1791563231572678 | Complete nginx/geodata candidate, rollback and real privacy/AOP fixtures | passed locally |
| REQ-P2-TRANSPORT | ANS-1791563232134870 | Exact native Realm, Naive listener and WARP version contracts | passed locally |
| REQ-P2-TRANSPORT | ANS-1791563232708226 | AWG/probe pin, unit and membership transition behavior | passed locally |
| REQ-P2-LIFECYCLE | ANS-1791563233266863 | Site full-to-minimal and owned/runtime/recovery preservation | passed locally |
| REQ-P2-OBSERVABILITY | ANS-1791563233830915 | Fresh/existing predictive task graphs, upgrade and full authority rollback | passed locally |
| REQ-P2-EVIDENCE | ANS-1791563234416737 | 45 focused policy/state/context tests; 49 adapter/expected-target tests; native real policy idle heartbeat and retirement plus fresh/retained sender check mode (8 passed); cohort-only watchdog regression | passed locally |
| REQ-P2-TRANSPORT | ANS-1791563234994294 | Bounded I01-I04 native packet/DNS/release-identity evidence and qualification | passed locally |
| REQ-P2-PUBLICATION | ANS-1791563234994294 | Bounded I05/I06 effective update and bearer-log evidence and qualification | passed locally |
| REQ-P2-ACCEPTANCE | ANS-1791563235717247 | Per-ID current-source coverage, preserved P1, independent review and complete local gate pass; exact-source hosted checks remain required | hosted gate pending |

## Audit coverage

All 32 confirmed findings F11-F42 have current source coverage. Existing P1 fixes remain in place.

| ID | Current correction | Observed evidence |
|---|---|---|
| F11 | Independent subscription TLS authority, hostname/key/expiry validation | Subscription nginx native and check-mode tests |
| F12 | Explicit evidence-account admission, terminal restricted Match, pre-mutation policy proof | Actual sshd denied-policy and forced-key tests |
| F13 | Read-only Tailnet probes execute during prediction, including bootstrap | Tailnet check-mode and audit regressions |
| F14 | XHTTP/Snell strict egress and valid transport expressions | Native nft syntax/enforcement |
| F15 | False update policy converges to effective absence | Native apt-config inspection |
| F16 | Disabled sshd jail converges to disabled effective policy | Native jail policy/transition checks |
| F17 | Typed bounded ban membership checks propagate failures | Fail2Ban helper failure-path tests |
| F18 | Atomic rules replacement retains timed dynamic sets | Native ban remaining-time and source removal tests |
| F19 | Fallback XHTTP access logging suppressed | Rendered vhost assertions |
| F20 | Proxy trust scoped to CDN vhost | Native nginx candidate/context tests |
| F21 | Verified paired geodata publication with compensation | Real file downloads, lock and failure tests |
| F22 | Complete nginx unit/config/credential transaction and rollback | Native HTTPS bad-key/unit compensation tests |
| F23 | Optional BBR isolated from mandatory sysctl failures | Native sysctl helper tests |
| F24 | Valid synthetic AOP chain and actual client assertions; CI scenario selected | Native trusted/untrusted/no-client tests; canonical Molecule pending |
| F25 | Exact supported Realm service and authenticated users schema | Exact pinned sing-box register/heartbeat/SSE/quota tests |
| F26 | AWG runtime and unit change restart intent | Controller notification proof; native tests cover membership/target retirement, not warm pin-only or unit-only adoption. |
| F27 | Recorded AWG membership retirement, unknown authority refusal | Native 2-to-1/rename/empty/foreign PartOf tests |
| F28 | Naive explicitly TCP HTTP/1 and HTTP/2 on configured port | Exact composite parser/listeners/authenticated CONNECT |
| F29 | Realm prerelease allowed only in canonical staging inventory | Production/unknown rejection tests |
| F30 | Required stable exact WARP package identity and signed metadata | Pin/identity controller tests; vendor registration unverified |
| F31 | Probe unit/context changes restart affected process | Native actual PID/context activation |
| F32 | Site dispatch reconciles bounded owned absence and retained state | Native timer/runtime-enable/mask/foreign/queued-handler tests |
| F33 | Read-only observability preflight, predictive candidate work omitted | Actual fresh/retained Ansible check mode with unchanged files |
| F34 | Existing runtime-change restart predicates retained and verified | Actual Ansible branch tests |
| F35 | Policy health at startup and while idle | Native empty-log daemon heartbeat |
| F36 | Bounded active windows and expiry/capacity accounting | Policy boundary tests |
| F37 | Exclusive bounded atomic metrics publication | Symlink/race/failure tests |
| F38 | Watchdog uses effective REALITY listener manifest | Cohort-only port regression |
| F39 | Strict complete recovery budget and durable atomic state | Malformed/symlink/hardlink preservation tests |
| F40 | Complete dead-man authority rollback with exact unit state | Native snapshot restore preserving replay-state advance |
| F41 | Unchanged convergence preserves previous generation | Native actual Ansible pointer inode test |
| F42 | Malformed nested evidence publishes redacted unhealthy result | Adapter and expected-target malformed CLI tests |

The six investigation candidates retain separate qualifications:

| ID | Result | Evidence and limit |
|---|---|---|
| I01 | Corrected supported IPv4-only split-hop contract | Owned original IPv6, including established flow, rejected; accepted client replies and unrelated host IPv6 preserved in real namespaces. |
| I02 | Corrected IPv4 split-hop source | Narrow marked WireGuard SNAT; actual encrypted packets exit Node B and return through Node A. |
| I03 | Corrected supported Unbound recursion boundary and compensating retirement | Authoritative query succeeds, non-local recursion refuses with no external packet. Full morphology artifact is unavailable and remains unverified; no feature task is closed. |
| I04 | Corrected release identity | Archive and source-commit release identities remain distinct; filesystem publication tests exercise both transitions. |
| I05 | Corrected effective package origins | Native apt-config confirms broader foreign origins are cleared and only the three security patterns remain. |
| I06 | Corrected bearer-log privacy | Actual nginx 502/429 log capture contains no bearer token and preserves categorical diagnostics. |

Both independent reviewers approve after authority/rollback corrections.
The older audit snapshot is not current runtime or production incident proof.

## Observed local runtime boundaries

- Policy daemon publishes startup and idle health from a real empty access log
  under its rendered systemd sandbox. Native enabled, disabled and repeated
  disabled convergence passed; no nftables mutation was needed for this case.
- Complete sender check mode passed in fresh and retained queue namespaces with
  real generated client certificates and exact release metadata. Role-owned
  filesystem snapshots were unchanged; this is preflight, not sender activation.
- Private receiver snapshot CLI restored credential bytes, verifier, unit files
  and generation links while preserving an advancing replay-state marker.
  Its exact prior active/enabled service record was retained.
- Shared runtime/rollback and collector source regressions passed 157 tests;
  agent source regressions and pointer execution passed 42 portable tests.
- No source/CI result here claims provider, fleet, public-path or human acceptance.

## Final local gate

The complete corrected build-gated `make check` passed. All 5,702 portable
tests and 22 subtests passed without skipped portable cases; 83 Linux-native
cases belong to the separately required native lane. All 56 shell tests, Rust
release tests and clippy passed. Source lint/syntax, policies, guards, schema
and all 150 template snapshots passed. All applicable pre-commit hooks pass.

The corrected task readers preserve assertions and follow enabled tasks and
publication blocks. The release-transition fixture explicitly establishes its
required parent mode under the machine gate's restrictive umask.

Local canonical CDN AOP Molecule creation/gathering reached its package step,
which refused Debian metadata signatures in the emulated amd64 container on
the arm64 test VM. Signature verification was preserved. Actual native AOP
client acceptance and the canonical hosted cdn-on scenario pass. Dedicated
package_updates and intrusion_prevention scenarios are now selected as well.
Baseline sysctl, CDN refresh and one policy authority context need bounded
hosted diagnostics; their production failure boundaries remain unchanged.
