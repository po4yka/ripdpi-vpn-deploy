# SCR-1793858662430806: Renew the REALITY self-steal certificate off-node on a schedule

## Objective

The P0 self-steal certificate is reissued off-node before it expires, into a new SOPS document ready for a reviewed deploy.

## Ownership

- `scripts/renew-self-steal-cert.py`, `scripts/install-operator-crons.sh`, the `renew-self-steal-cert` Make target, `docs/how-to/certificates.md`, `ansible/roles/reality-self-steal/CLAUDE.md`, `tests/unit/test_renew_self_steal_cert.py`.

## Execution

- [ ] SCR-1793859258666469 Reissue the self-steal pair off-node only when due into a new SOPS document #feature @item:SCR-1793858662430806
- [ ] SCR-1793859672819587 Schedule the daily renewal check in the operator cron installer #feature @item:SCR-1793858662430806
- [ ] SCR-1793860092575094 Document the renewal and reviewed deploy procedure #feature @item:SCR-1793858662430806

## Verification

- Unit tests with sops and lego stubs; a real-sops run on an encrypted copy of the P0 document; a not-due run against the live P0 document; shellcheck and docs-check; remote CI.
