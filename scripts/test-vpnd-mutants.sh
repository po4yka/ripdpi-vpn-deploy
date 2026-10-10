#!/usr/bin/env bash
# Run full mutation checks in a tracked working-tree copy. Exit 2 exclusively
# means valid completed results contain survivors; technical failures stay red.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/vpnd-mutants.XXXXXX")"
scratch="$(cd "$scratch" && pwd -P)"
trap 'rm -rf "$scratch"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if (( $# != 0 )); then
  echo "Mutation checks do not accept a partial selection" >&2
  exit 1
fi
if ! git -C "$root" ls-files -z | tar -C "$root" --null -T - -cf - | tar -C "$scratch" -xf -; then
  echo "Cannot prepare mutation source tree" >&2
  exit 1 # Copy failure is never a surviving-mutant verdict.
fi

python3 "$root/scripts/prepare-vpnd-mutation-tree.py" "$scratch"
cd "$scratch"
# Both direct imports and subprocess launchers resolve the generated source.
export PYTHONPATH="$scratch/mutants/src"
set +e
mutmut run --max-children 2
run_status=$?
# mutmut 3.8 exports the structured inventory with a separate command.
mutmut export-cicd-stats
export_status=$?
set -e

# Retain each invocation independently, including technical-failure output.
# Never remove another run's report or mutate the caller's source tree.
mkdir -p "$root/vpnd/mutants"
report="$(mktemp -d "$root/vpnd/mutants/run.XXXXXX")"
if [[ -d mutants ]]; then
  cp -R mutants/. "$report/"
fi
if (( run_status != 0 )); then
  if (( run_status == 2 )); then
    echo "Mutation backend failed; exit 2 is reserved for verified survivors" >&2
    exit 1
  fi
  exit "$run_status"
fi
if (( export_status != 0 )); then
  if (( export_status == 2 )); then
    exit 1
  fi
  exit "$export_status"
fi
python3 "$root/scripts/check-vpnd-mutation-results.py" "$report/mutmut-cicd-stats.json"
