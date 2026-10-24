## Context

The pipeline installs event-loop signal handlers, but review temporarily
replaces them and blocks in a terminal `readline`. A worker-directed signal
sets Python's pending handler state without waking that blocking main-thread
read. The real-launcher reproduction stops only after terminal input arrives.

## Goals / Non-Goals

- Goal: a review responds to handled signals without user input and completes
  cleanup before exit, with the existing approval and process boundaries.
- Goal: cancellation releases terminal state and awaits owned cleanup.
- Non-goal: change command flags, runner process ownership, other wizard flows,
  dependencies, provider operations or any Terraform/Ansible runtime state.

## Decisions

- Keep `StopSignals` as the only signal owner throughout pipeline, review and
  cleanup. Record the first handled signal and notify an async waiter. Preserve
  inherited ignored handlers. Remove the separate review signal handler path.
- Add a terminal reader that uses the event loop and nonblocking descriptor
  reads. Keep stderr terminal admission and the existing stdin-or-controlling-
  terminal rule. Do not consume piped answers. Restore descriptor flags, remove
  reader registration and close only owned descriptors on every exit.
- Consume exactly one line per confirmation. Read bounded data without a
  blocking `readline`; preserve encoding, prompt text, invalid-answer handling
  and defaults. Move both initial deploy/reconverge confirmations to this path
  so a synchronous text buffer cannot prefetch the later review answer.
- Await review answer and signal notification together. Check the recorded
  signal before accepting a ready answer and before the gated Make call. Cancel
  and await prompt-owned waiters before cleanup. Explain opens no terminal.
- Catch task cancellation at the pipeline boundary. Retain and await the
  cleanup task through later cancellation; preserve the primary error. A stop
  signal does not cancel the running Make step or its capture worker.
- Reject polling sleeps, timeout increases and a background stdin thread:
  these do not give the prompt a clear cancellation and resource lifetime.

## Contracts and ownership

- The implementer owns `vpnd/src/vpnd/wizard/async_prompts.py`, its export,
  `commands/__init__.py`, `commands/deploy.py`, `commands/reconverge.py`,
  wizard/lifecycle tests and `vpnd/CLAUDE.md`. Root owns planning and acceptance.
- `runner/process.py`, command flags, generated command references and all
  infrastructure layers retain their existing contracts.
- Test-only permission/interpreter fixture repairs already reviewed in the
  hopping branch are included as local-gate prerequisites. They change no
  production validation or permission policy.

## Risks / Trade-offs

- Descriptor flags affect the open file description: save and restore them in
  a synchronous cleanup block and test cancellation, EOF and partial input.
- Buffered answers can cross prompt boundaries: use one async input path for
  both confirmations and test queued initial/review answers.
- An answer and signal can become ready together: the signal check wins before
  mutation. Test the boundary deterministically.
- Repeated cancellation can detach cleanup: keep task ownership explicit and
  prove cleanup completion and primary-error preservation.
- A fixture can hide the bug: use the actual launcher and PTY, deliver each
  signal to a retained worker, and inspect actual synthetic plaintext removal.

## Migration Plan

No data migration, CLI flag change or dependency update is needed. Update all
internal review call sites in one change; do not keep a synchronous adapter.
Run red/green PTY regressions, wizard/lifecycle/runner tests, full vpnd tests,
lint and parity, package validation and the full local gate. Review and merge
through a separate PR, then observe exact-main CI before source acceptance.
Validate the installed package's prompt path with synthetic inputs. A source
revert restores the old signal defect, so it is not a preferred recovery path.
No live deployment is part of validation or rollout.
