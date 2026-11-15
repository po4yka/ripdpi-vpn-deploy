---
task_id: XRY-1794729068388916
change: xry-1794729068388916-single-tls-identity-and-decoy
commit_sha: cfd8a6140f21620eb4d7f7b42502763c3bcb4a9a
local: passed
local_evidence: "Focused checks on the working tree of 7940b9c1, each exit 0: pytest for test_reality_self_steal.py, test_tls_identity_preflight.py, test_public_site_contract.py, test_nginx_xhttp_bearer_logs.py, test_validate_reality_target.py, test_monitor_reality_target.py, test_validate_ansible_extra_vars.py, test_deploy_controller.py, test_operator_automation.py, test_sshd_ownership.py and test_transport_site_transaction.py; ansible-lint on the reality-self-steal, nginx-xhttp, xray, hysteria and node_manifest roles and site.yml; make snapshot-check; make shellcheck; make docs-check; openspec validate --strict; the commit hooks. Removing each fix makes a test fail. One independent review; its duplicate default_server finding and its Hysteria default finding were fixed before the commit. Not run: make check (the lead runs it on the integrated branch), Molecule (the pinned image has no arm64 manifest) and the native Linux test test_xhttp_endpoint_contract_native.py. A wider run of 87 unit files had failures only in test_observability_p2_runtime.py and test_observability_protocol_liveness_adapter.py (platform and capability checks in files this change does not touch) and in test_repository_identifier_policy.py (addresses in test_doh_lookup.py on the base branch). Integrated gate on the tree of cb173d5a, before its rebase onto two task-bookkeeping commits of main (all six tasks on one branch): make -k -j 4 check passed every target except test-unit, where 12170 cases passed and one failed, test_tailnet_network_executor.py::test_expiry_serializes_with_forward_mark_and_rolls_back_true; it is timing-sensitive under the parallel run, passes alone and with its file, and this branch changes no tailnet code."
remote_ci: passed
remote_ci_evidence: "The reality-self-steal and nginx-xhttp Molecule scenarios passed in CI run 43712765464 on main at 827d555e. The native XHTTP endpoint test ran there for the first time and failed for both ports at tests/unit/test_xhttp_endpoint_contract_native.py line 154: the test split a text-mode response at CRLF CRLF. The commit 'test(nginx-xhttp): split the 404 response at the text-mode separator' corrects the split. CI run 43739972596 on main at 00daf904 passed all 84 jobs; its native runtime integration lane 3/4 ran test_xhttp_endpoint_contract_native.py and every case passed, and the nginx-xhttp and reality-self-steal Molecule scenarios passed."
dry_run: passed
dry_run_evidence: "On 2026-11-15 the full dry-run at 25847e91 refused on node-a before any change: a production host needs an operator-owned self-steal site directory. With the directory set, the full dry-run at 00daf904 exited 0 on node-a, node-b and node-c with 0 failed and 0 unreachable; the TLS identity preflight passed on each node."
staging: required
staging_evidence: Pending a staging deploy with managed TLS and with a supplied certificate, to observe port 80 on a real nginx.
live: required
live_evidence: "Partly done on 2026-11-15. The deploy at 00daf904 passed deploy, verify, source-drift, security-verify, smoke-test and protocol-liveness on node-a, node-b and node-c. An outside scan of the three production addresses showed one certificate identity for each address: node-a answers on TCP/443 only, with one certificate with and without SNI, and its root page is the operator site, not a bundled page; node-b answers on TCP/80 and TCP/443 with one certificate, port 80 redirects to HTTPS on the same name (XHTTP is on 443) and an unknown Host gets 404; node-c answers on UDP/443 only, with one certificate for its own name and no certificate without SNI or for another name. Pending: the operator site tree on node-a and node-b has four files that are byte-identical to the repository scaffold (404.html, assets/site.css, favicon.svg, logo.svg); the operator must replace them before this category passes."
client: not_applicable
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TMD-SELF-STEAL-OWNED-DECOY | XRY-1794729166198238 | `test_reality_self_steal.py` runs the role's own tasks through `ansible-playbook`: production refusal, bundled site on a non-production host, operator tree with a nested binary file and the retired bundled page, refusal without `index.html` or `404.html`; `test_deploy_controller.py` and `test_validate_ansible_extra_vars.py` for the controller input. No new Molecule case; the existing scenarios are pending CI | passed |
| REQ-PROTO-RTV-NETWORK | XRY-1794729177636809 | `test_validate_reality_target.py`: the four values with a stub lookup, the real script against a loopback resolver (same, different, failed lookup, exit 0, no address or AS number in the output), no query without `NODE_ADDRESS` or in `owned-public` mode | passed |
| REQ-TMD-SINGLE-IDENTITY | XRY-1794729177636809 | `test_tls_identity_preflight.py` runs the real task: refusals with the listener names and the three ways to pass, self-steal, exception, non-production and P0 passes, the committed profiles that refuse on production, the manifest flag without the reason | passed |
| REQ-TMD-PORT-80-DECOY | XRY-1794729189657998 | `test_public_site_contract.py` on the rendered servers (supplied and managed TLS, port 443 and 8443, unknown Host), `test_nginx_xhttp_bearer_logs.py`, the snapshot; the Molecule requests and the native test on a real nginx passed in CI run 43739972596 on main at 00daf904 | passed |
