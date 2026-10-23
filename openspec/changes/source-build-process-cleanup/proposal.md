# Change: Confirm source build process cleanup before publication

Task ID: `ANS-1792773060904443`

## Why

The shared source-build helper can reject a successful build while checking its process group on macOS. The failure occurs on the old dependency lock as well as the updated lock. It prevents completion of the local gate for the dependency update. Build descendants must still terminate before publication and lock release.

## What Changes

- Keep exact process-group authority until foreground work and cleanup finish.
- Confirm successful completion without classifying transient process-exit state as a live build.
- Retain bounded cancellation, timeout and descendant cleanup with explicit failure when cleanup cannot be confirmed.
- Correct asynchronous test synchronization for process exit and fixture publication.
- Verify the complete local gate and protected hosted checks before integration. No public command or descriptor contract changes are planned.

## Capabilities

### New Capabilities

- `ansible/source-build-process-lifecycle`: own the foreground build session through completion, cancellation and cleanup.

### Modified Capabilities

- None.

## Impact

- Ansible shared runtime source-build helper and its portable regression tests.
- Local monitor, smoke and transaction test synchronization where the observed failures require a correction.
- No live deployment, provider, credential or transport change.
