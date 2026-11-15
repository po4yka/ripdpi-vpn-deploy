## Context

`proposal.md` gives the motivation. `transport_runtime_rollback.py` calls `tx.apply()` for the `config` action; `refuse_revocation_rollback()` runs only in `compensate_latest()` and `recover()`. The subscription service reads a revoked-hash file for `/sub/`, while nginx serves `/share/<token>/` from a directory named by the token. `issue-bootstrap.sh` already uses strict host-key checking and no agent; `issue_sub_token.py` does not. The mirror unit and the service unit both run as `vpn-bootstrap`.

## Goals / Non-Goals

- Goal: no rollback or static path returns a credential after revocation.
- Goal: a device payload leaves the workstation or the subscription host only toward a pinned host key.
- Non-goal: how the first key of a new node is obtained. `SEC-1794287701595900` owns that.
- Non-goal: encryption of subscription documents at rest. It needs a client contract change and is not part of this change.

## Decisions

- The rollback compares client identities, not only the revocation record. `restore_points` writes the old configuration to `config.json.prev` on every configuration change, so after a revocation that file holds the revoked client. The `config` action also calls `refuse_revocation_rollback()` for the accepted receipt. Rejected: only call `refuse_revocation_rollback()`, because a client removed by an ordinary converge has no revocation record.
- `revoked-hashes.yml`, which both the normal role and the retained-publisher flow import, removes every share directory whose name hashes to a revoked entry; the share token is the subscription token, so the deny list identifies the bundle. The upload tasks skip a declared token that is revoked. Rejected: proxy `/share/` through the service, because it adds a second code path for static files.
- Undeclared bundles are not pruned. `vpn.share_bundles` is an upload selection for one run, and the role keeps retained bundles on purpose; an existing test pins that. The first draft of this change pruned them, which would have ended every recipient link on a run that declared no bundles.
- `issue_sub_token.py` (`payload_ssh`) and `issue-bootstrap.sh` use one option set: `-F /dev/null`, the SSH port from the provider output, `BatchMode=yes`, `StrictHostKeyChecking=yes`, `ForwardAgent=no`, `ProxyCommand=none`, no global known-hosts file, and the pinned file from `INSPECT_KNOWN_HOSTS` (default `~/.ssh/known_hosts`), which the deploy and inspection commands already use. `ANSIBLE_SSH_PRIVATE_KEY_FILE` selects the key and then disables the agent. `SUBSCRIPTION_SSH_HOST` names the host when the operator reaches it by a management address, because a `HostName` rule in the SSH configuration no longer applies. A failed SSH connection is reported as such and not as mirror mode. The two scripts are Python and shell, so the list is written once in each.
- The mirror is split into two units. `vpn-sub-mirror-fetch.service` runs rsync or restic as a new `vpn-sub-mirror` user into `/var/lib/vpn-sub-mirror/incoming`; that user owns the credential directory. `vpn-sub-mirror.service` requires it, still runs as the delivery service user, and copies the fetched tree into its stage before the existing validation and pointer switch. The copy makes the service user the owner of every published node, so no step needs root or `chown`. The fetched directory is `vpn-sub-mirror:vpn-bootstrap 0750`: the service user reads it through its group and no other user can enter it. Rejected: one unit as root, because it would run the network clients with more privilege than today.
- The host key is a new secret, written to a file that only the mirror user reads. `mirror.ssh_opts` admits only a port, an `rsync://` source is refused, and the fetch unit has a start timeout. The fetch directory is fixed at `/var/lib/vpn-sub-mirror`, so no input can make the role re-own another directory. The pull runs outside the publisher lock; the fetch replaces its directory by one rename and the publisher refuses a tree that changed, or that it could not read completely, during its copy.
- `rotate-secrets.sh` runs `sops rotate --in-place` after `sops updatekeys`. Both run on the file in place, because sops finds its recipient rules from the file path; the script keeps a private copy beside the file and restores it when either step fails or the run is interrupted.

## Contracts and ownership

- Ansible: `ansible/roles/runtime-release/files/transport_runtime_rollback.py`; `ansible/roles/subscription-host/` tasks, templates, defaults and Molecule.
- Scripts: `scripts/issue_sub_token.py`, `scripts/issue-bootstrap.sh` (helper reuse only), `scripts/rotate-secrets.sh`.
- Secrets: `secrets/schema.json` and `secrets/prod.secrets.example.yaml` gain the mirror host-key value; `scripts/check-secrets-coverage.py` covers it.
- Docs: `docs/how-to/multi-operator.md` and `docs/reference/secrets.md` state the data-key rotation.

## Risks / Trade-offs

- A legitimate rollback is refused after a device was removed → the helper prints the refusal category (`rollback-readmits-client`), the rollback guide explains it, and the operator converges the current configuration instead.
- The mirror stops until the operator supplies the host key → the role fails in preflight with the name of the missing value.
- Data-key rotation rewrites the whole encrypted file → the diff is large but the plaintext is unchanged; `sops rotate` must decrypt the file, so a recipient set that cannot decrypt it fails the run and the copy is restored.

## Migration Plan

Merge, add the mirror host-key secret where the mirror is enabled, then deploy the subscription host and the transport nodes through the ordinary dry-run and deploy transaction. Rollback is a revert and a second deploy; the role's disable path removes the fetch unit and script, and the `vpn-sub-mirror` user and its directories stay until an operator removes them. Gates: the focused unit tests, the transport runtime transaction unit tests, `make molecule-test ROLE=subscription-host`, `make snapshot-check`, `make shellcheck`, and one `make check` before handoff.
