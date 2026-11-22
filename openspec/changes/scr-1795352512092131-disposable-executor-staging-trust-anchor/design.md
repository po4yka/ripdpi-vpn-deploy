## Context

See proposal.md. The disposable executor is an exact, non-default Colima profile that `make prepare-disposable-liveness` creates and `make deonboard-disposable-liveness` (or `retire-unbound-staging-executor`) deletes. `make provision-disposable-liveness-runtime` already installs pinned packages and engines into it as root through `colima ssh`. sing-box and Xray verify TLS against the Linux system store (`/etc/ssl/certs/ca-certificates.crt`); a self-signed certificate in that store is accepted as its own anchor. `scripts/ci-real-deploy.py` installs the run's `nginx_xhttp.cert_pem` into its runner's store the same way.

## Goals / Non-Goals

- Goal: a disposable staging node with generated self-signed TLS passes the four-profile proof on the operator executor, with TLS verification enabled.
- Non-goal: ACME issuance for staging. A staging DNS name needs an operator-owned zone and DNS credentials that the disposable flow does not hold; managed HTTP-01 remains the production path.
- Non-goal: a trust anchor on fleet sentinels or the `liveness-sentinel` role.

## Decisions

- Add the anchor to the existing provisioning step instead of a new Make goal: the executor is provisioned once per run, after staging secrets exist, and before the sentinel installer's first authenticated probe. Rejected: a separate goal (more lifecycle surface for one file copy).
- Validate locally with the pinned `cryptography` library (already a `requirements.txt` dependency) before the first executor command: at most 64 KiB read, exactly one PEM block and it is a certificate (so a private key in the file refuses), `verify_directly_issued_by` on itself (issuer equals subject and its own key signed it), the current time inside its validity period, and exactly one subject alternative name, a non-wildcard DNS name, which is what the generator writes. Rejected: `openssl verify -CAfile X X`, which does not check the anchor's own signature without `-check_ss_sig` and depends on the local openssl flavour (LibreSSL on macOS); name-pattern constraints on that name, because the generator's server name is operator-chosen; per-profile certificate pinning, which would change the public liveness profile contract; and a `CA:FALSE` requirement, which would refuse the generator's own `openssl req -x509` output.
- `ca-certificates` joins the executor package list when an anchor is given, so `update-ca-certificates` exists. Install path `/usr/local/share/ca-certificates/ripdpi-staging-anchor.crt` (one fixed name, so a second provisioning replaces, not accumulates) with mode 0644 through the existing root `install` helper, then `update-ca-certificates`.
- The operator extracts only the public certificate (`sops --decrypt --extract '["nginx_xhttp"]["cert_pem"]'`) into the private run directory; the private key never leaves SOPS. The generator writes the same certificate to `hysteria.cert_pem`, so one anchor covers `p1-xhttp` and `p2-hysteria2`; `p0-reality` and the AWG probe need none.

## Contracts and ownership

- Script: `scripts/provision-disposable-liveness-runtime.py` gains `--trust-anchor`.
- Make: `provision-disposable-liveness-runtime` allows the `STAGING_TRUST_ANCHOR` command-line field and passes it only when set.
- Docs: `docs/reference/protocol-liveness.md` disposable executor section.

## Risks / Trade-offs

- A trusted self-signed anchor with `CA:TRUE` lets its key holder sign any name for this executor → the executor is disposable, deleted at de-onboarding, carries only probe traffic, and the key exists only on the disposable node.
- An operator could pass a wrong certificate → the probe then refuses exactly as before; nothing is weakened.

## Migration Plan

Additive and optional. Rollback: revert the commit; executors without the anchor behave as before. Gate: unit tests, `make docs-check`, then one disposable staging run with fresh `ok` on all four profiles.
