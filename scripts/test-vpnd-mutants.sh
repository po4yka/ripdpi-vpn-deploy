#!/usr/bin/env bash
# Mutate a disposable copy of tracked working-tree files, including the
# sibling docs, fixtures and scripts required by vpnd's build and tests.
# Stage new source files before running. Never mutate the caller's checkout.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/vpnd-mutants.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! git -C "$root" ls-files -z | tar -C "$root" --null -T - -cf - | tar -C "$scratch" -xf -; then
  echo "Cannot prepare mutation source tree" >&2
  exit 1 # tar's exit 2 is a setup failure, never a surviving-mutant verdict.
fi

# Retain only build artifacts and mutation reports outside the temporary tree.
# In-place execution is serial; compiler parallelism is bounded separately by
# the operator's top-level build-gate / CARGO_BUILD_JOBS.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$root/vpnd/target}"
cd "$scratch/vpnd"
cargo mutants --in-place --no-shuffle --output "$root/vpnd" "$@"
