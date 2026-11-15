## Context

`proposal.md` gives the motivation. `transport_runtime_rollback.py` calls `tx.apply()` for the `config` action; `refuse_revocation_rollback()` runs only in `compensate_latest()` and `recover()`. The subscription service reads a revoked-hash file for `/sub/`, while nginx serves `/share/<token>/` from a directory named by the token. `issue-bootstrap.sh` already uses strict host-key checking and no agent; `issue_sub_token.py` does not. The mirror unit and the service unit both run as `vpn-bootstrap`.

## Goals / Non-Goals

- Goal: no rollback or static path returns a credential after revocation.
- Goal: a device payload leaves the workstation or the subscription host only toward a pinned host key.
- Non-goal: how the first key of a new node is obtained. `SEC-1794287701595900` owns that.
- Non-goal: encryption of subscription documents at rest. It needs a client contract change and is not part of this change.

## Decisions

- The rollback compares client identities, not only the revocation record. The first step of this change is a test that shows whether a normal revocation rewrites `config.json.prev`; the comparison holds in both cases. Rejected: only call `refuse_revocation_rollback()`, because a client removed by an ordinary converge has no revocation record.
- The revocation path removes the share directory in the same publisher call that records the revoked hash. Rejected: proxy `/share/` through the service, because it adds a second code path for static files.
- Converge prunes the share root against the declared list, with the same owner and mode checks as the existing copy task.
- The SSH options for payload calls come from one helper that `issue-bootstrap.sh` and `issue_sub_token.py` share: `-F /dev/null`, `BatchMode=yes`, `StrictHostKeyChecking=yes`, `ForwardAgent=no`, and the pinned `UserKnownHostsFile`.
- The mirror gets a `vpn-sub-mirror` system user. It writes into a staging directory that the service user reads through a group. The host key is a new secret that the role writes to a root-owned `known_hosts`.
- `rotate-secrets.sh` runs `sops rotate --in-place` after `sops updatekeys`, on a copy, and replaces the file only when both succeed.

## Contracts and ownership

- Ansible: `ansible/roles/runtime-release/files/transport_runtime_rollback.py`; `ansible/roles/subscription-host/` tasks, templates, defaults and Molecule.
- Scripts: `scripts/issue_sub_token.py`, `scripts/issue-bootstrap.sh` (helper reuse only), `scripts/rotate-secrets.sh`.
- Secrets: `secrets/schema.json` and `secrets/prod.secrets.example.yaml` gain the mirror host-key value; `scripts/check-secrets-coverage.py` covers it.
- Docs: `docs/how-to/multi-operator.md` and `docs/reference/secrets.md` state the data-key rotation.

## Risks / Trade-offs

- A legitimate rollback is refused after a device was removed → the refusal names the reason, and the operator converges the current configuration instead.
- The mirror stops until the operator supplies the host key → the role fails in preflight with the name of the missing value.
- Data-key rotation rewrites the whole encrypted file → the diff is large but the plaintext is unchanged; the existing decrypt check runs after the rotation.

## Migration Plan

Merge, add the mirror host-key secret where the mirror is enabled, then deploy the subscription host and the transport nodes through the ordinary dry-run and deploy transaction. Rollback is a revert and a second deploy; the new user and directory are removed by the role's cleanup. Gates: the focused unit tests, the transport runtime transaction unit tests, `make molecule-test ROLE=subscription-host`, `make snapshot-check`, `make shellcheck`, and one `make check` before handoff.
