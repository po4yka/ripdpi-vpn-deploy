#!/usr/bin/env bash
# Run one scheduled command and propagate failures from the command and syslog.
set -euo pipefail
tag=$1
shift
"$@" 2>&1 | logger -t "$tag"
