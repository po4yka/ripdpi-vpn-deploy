## Context

The existing helper reaps the command leader before checking its group. A real macOS probe also confirms that an unreaped zombie-only group returns EPERM for signal zero and termination. Group existence alone cannot identify a live descendant. Python on this macOS does not expose waitid.

## Goals / Non-Goals

- Goal: retain exact process authority, reject surviving descendants and preserve the source-build transaction.
- Goal: make portable tests observe completed asynchronous work and pass the full local gate.
- Non-goal: change consumer descriptors, receipts, public commands, deployed hosts or transport behavior.

## Decisions

- Use a private session supervisor and a command guardian. The supervisor owns the session. The guardian is a non-session leader in its own process group and runs the actual command there.
- After command completion or cancellation, the guardian moves into the supervisor group before it acknowledges detachment. It stays alive. Its allocated PID reserves the old group number while the old group contains only command descendants.
- Probe and signal the old group only after confirmed detachment. The guardian performs these operations while alive; the supervisor may perform fallback cleanup only while it keeps the guardian unreaped. The caller never signals a numeric group from a stale acknowledgement. A live group after successful command exit causes build refusal and cleanup. EPERM remains unknown; bounded confirmation must reach ESRCH before successful cleanup.
- Release and reap both guardians only after group cleanup is confirmed. Control-channel EOF also requests owned cleanup. Bound every protocol message and control wait. A failed or lost acknowledgement fails closed.
- Consume queued cancellation records while waiting for release under one fixed deadline. Require the caller's default child-reaping disposition before execution, and set that disposition explicitly in the private supervisor. Ignored or custom SIGCHLD handling cannot supply the required PID ownership proof.
- Preserve command argv, environment, output suppression and retained-directory execution. Control and status descriptors never enter the actual command. Keep cancellation and failure causes; cleanup cannot convert refusal into success.
- Keep monitor exit checks asynchronous and bounded. Publish synthetic PID records atomically. For transaction test setup, batch only equivalent preparatory API calls while retaining real journal and fsync behavior.
- Measure smoke fixture execution before selecting a performance change. Keep the complete source task graph and its safety assertions. Any test timeout must also reclaim the owned subprocess session.
- Use pipelining in the unprivileged local smoke fixture. A real Snell profile reduced transport operations from 65 to 16 while keeping all source tasks and the target file copy. Keep the 45-second deadline and all cleanup assertions.

## Contracts and ownership

- Runtime worker: `ansible/roles/runtime-release/files/runtime_build_receipt.py`, `tests/unit/test_runtime_build_receipt.py` and the runtime-release role notes.
- Test worker: monitor, smoke and site transaction test fixtures, plus test notes. The primary maintainer serializes shared test-note edits.
- Primary maintainer: portfolio and OpenSpec records, full validation, review and publication.
- Terraform, cloud-init, secrets, deployment inputs, public CLI and receipt formats are unchanged. The helper uses the existing Python standard library.

## Risks / Trade-offs

- Two small guardians add process-start cost. They retain group identity without a platform-specific process inventory or a new package.
- Cancellation during startup or detachment can lose an acknowledgement. Regression tests must exercise those windows and verify that no owned child escapes.
- A process-control error can leave cleanup unconfirmed. Preserve categorical refusal and the primary cause; never infer that the group is gone.
- Trusted commands can deliberately leave their session. The existing foreground-only consumer contract remains in force.

## Migration Plan

No data migration is required. Existing role installation publishes the updated helper on a future authorized deployment. This work validates source only. Reverting the source change restores the previous helper without changing receipts.

Run failing regressions first, then the complete affected files, role Molecule where available, full local `make check`, independent security review and protected hosted checks. Commit review evidence before terminal task transitions. Archive the linked change and close both tasks only after their actual gates pass.
