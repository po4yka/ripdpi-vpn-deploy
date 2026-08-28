# Change: Deliver authenticated fleet probes and passive inspection

Task ID: `TST-1787850553468536`

## Why

The fullstack sentinel installer requires an XHTTP outbound that the official
sing-box emitter intentionally excludes. Probe curl invocations inherit ambient
proxy settings, so successful HTTP alone can misrepresent the chosen path.
Current verification also invokes the repair watchdog; Ansible check mode is not
a passive inspection boundary. Backup timer activity does not establish a
successful restore or an offsite copy.

## What Changes

- Expose a separate passive fleet inspection command with explicit host scope,
  pinned SSH identity, bounded reads, and redacted service/source/backup evidence.
- Keep active probes separate from passive inspection and repair. Neither new
  inspection nor active liveness invokes automatic service restart or rotation.
- Complete four-profile onboarding with the existing Xray XHTTP adapter, exact
  runtime pins, dedicated client credentials, and explicit AWG host selection.
- Isolate curl from ambient configuration and proxy bypass settings.
- Make restore cleanup conditional on owning the temporary target; reject an
  existing target without deleting it. Keep retention and remote settings intact.
- BREAKING: fullstack sentinel configuration requires an Xray runtime pin and
  explicit AWG source binding; update every repository caller and example.
- Distinguish one-vantage IPv4 probe proof from filtered-path, UDP payload,
  IPv6, Android client, rotation, and offsite recovery acceptance.

## Capabilities

### New Capabilities

- `operations/fleet-observation`: passive inspection and separately invoked,
  authenticated probes with truthful provenance and failure classification.

### Modified Capabilities

- None. Existing liveness implementation is extended without changing the
  independent probe-matrix evidence schema or recurring AWG acceptance contract.

## Impact

- Makefile; liveness installer, sentinel, evaluator, and matrix curl adapter;
  Python/shell tests; operator documentation and liveness configuration contract.
- Backup restore-drill template and its existing contract tests, limited to
  temporary-resource ownership and cleanup; no backup pruning or sandbox refactor.
- Uses existing trusted runtimes and SOPS materialization. No new production
  dependency, cloud resource, public panel, or provider rule is introduced.
- Offsite configuration and isolated restore use existing backup behavior. An
  approved destination and recovery credentials remain operational prerequisites;
  this change does not invent an upload destination or run retention pruning.
