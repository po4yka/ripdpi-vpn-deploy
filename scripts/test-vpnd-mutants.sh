#!/usr/bin/env bash
# Run full mutation checks in a tracked working-tree copy. Exit 2 exclusively
# means valid completed results contain survivors; technical failures stay red.
set -euo pipefail

mutation_environment=("PATH=$PATH" "LANG=C" "LC_ALL=C" "PYTHONUTF8=1" "PYTHONNOUSERSITE=1")
clean() { env -i "${mutation_environment[@]}" "$@"; }

root="$(cd "$(clean dirname "$0")/.." && pwd -P)"
scratch="$(clean mktemp -d /tmp/vpnd-mutants.XXXXXX)"
scratch="$(cd "$scratch" && pwd -P)"
trap 'clean rm -rf "$scratch"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Mutated guards must never fall through to operator configuration or
# credentials. Only public tool paths and the already-acquired gate survive.
mutation_environment+=(
  "HOME=$scratch/home" "XDG_CONFIG_HOME=$scratch/config"
  "XDG_CACHE_HOME=$scratch/cache" "XDG_DATA_HOME=$scratch/data"
  "XDG_STATE_HOME=$scratch/state" "XDG_RUNTIME_DIR=$scratch/runtime"
  "TMPDIR=$scratch/tmp" "PYTHONPATH=$scratch/mutants/src"
  "GIT_CONFIG_GLOBAL=/dev/null" "GIT_CONFIG_NOSYSTEM=1"
  "CARGO_BUILD_JOBS=2" "CMAKE_BUILD_PARALLEL_LEVEL=2"
)
if [[ ${BUILD_GATE_HELD:-} == 1 ]]; then
  mutation_environment+=("BUILD_GATE_HELD=1")
fi
clean mkdir -p "$scratch"/{home,config,cache,data,state,runtime,tmp}

if (( $# != 0 )); then
  echo "Mutation checks do not accept a partial selection" >&2
  exit 1
fi
if ! clean git -C "$root" ls-files -z | clean tar -C "$root" --null -T - -cf - | clean tar -C "$scratch" -xf -; then
  echo "Cannot prepare mutation source tree" >&2
  exit 1 # Copy failure is never a surviving-mutant verdict.
fi

clean python3 "$root/scripts/prepare-vpnd-mutation-tree.py" "$scratch"
cd "$scratch"
set +e
clean mutmut run --max-children 2
run_status=$?
# mutmut 3.8 exports the structured inventory with a separate command.
clean mutmut export-cicd-stats
export_status=$?
set -e

# Retain each invocation independently, including technical-failure output.
# Never remove another run's report or mutate the caller's source tree.
clean mkdir -p "$root/vpnd/mutants"
report="$(clean mktemp -d "$root/vpnd/mutants/run.XXXXXX")"
if [[ -d mutants ]]; then
  clean cp -R mutants/. "$report/"
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
clean python3 "$root/scripts/check-vpnd-mutation-results.py" "$report/mutmut-cicd-stats.json"
