# ANS-1791586652330612: Complete remaining role audit improvements

## Objective

Deliver I07-I15/F43 as runnable source contracts, preserve I01-I06 corrections
and qualifications, and extend existing PR 282 with verified code.

## Ownership

- Host worker owns `ansible/roles/{subscription-host,reality-self-steal,honeypot,monitoring,security_audit}/` and `ansible/roles/warp-outbound/molecule/`; associated uniquely named tests and role notes. I07/I09/I13/I14/I15/F43.
- Runtime worker owns `ansible/roles/nginx-xhttp/files/nginx_transaction.py`, `ansible/roles/nginx-xhttp/tasks/transaction.yml`, `ansible/roles/geodata/`, `ansible/roles/naive/`, `ansible/roles/policy-ratelimit/`, `ansible/roles/observability_deadman/`; uniquely named/direct activation, auth, tail and notification tests plus notes. I08/I10/I11/I12. It is the sole writer of shared activation helpers; host self-steal consumes that interface through coordinated messages.
- Primary owns `secrets/schema.json`, `secrets/prod.secrets.example.yaml`, `scripts/`, `vpnd/`, `ansible/group_vars/`, shared observability endpoint consumers under `observability_agent/`, all generic fixtures/shared tests, snapshots, CI, docs and task/spec artifacts. All other shared requests go through primary. No worker stages or commits, reads private inputs, changes default contexts, or touches another lane. Preserve P1/P2 and unrelated work.

## Execution

- [x] ANS-1791587032080262 Bound bootstrap audit and consumption history behind durable retirement authority #feature @item:ANS-1791586652330612
- [x] ANS-1791587032645227 Reconcile interrupted nginx and geodata activation and isolate self-steal TLS publication #feature @item:ANS-1791586652330612
- [x] ANS-1791587033216706 Deliver per-device Naive issuance revocation and native independent access #feature @item:ANS-1791586652330612
- [x] ANS-1791587033777473 Recover truncated policy inputs count all honeypot observations and share private scrape endpoints #feature @item:ANS-1791586652330612
- [x] ANS-1791587034315130 Persist recovery notification intent through delivery failure and restart #feature @item:ANS-1791586652330612
- [x] ANS-1791587034859002 Require successful opt-in audit collection and prove WARP role reconvergence #feature @item:ANS-1791586652330612
- [ ] ANS-1791587035398569 Preserve prior investigation boundaries and complete source native CI review and PR delivery #feature @item:ANS-1791586652330612

## Verification

Focused positive/failure/boundary tests; actual consumed-grant replay and bounded
storage; SIGKILL/interleaved activation and TLS publication; exact pinned native
Caddy two-device authentication/revocation; real private socket/scrape and Lynis
machine-report proof; recovery retry through restart and stale completions;
relevant canonical Molecule, reviewed snapshots, schema/coverage/profile/listener
checks, full build-gated make check, independent security review and all exact-
source hosted checks. Live/provider/client/human acceptance are outside scope.
