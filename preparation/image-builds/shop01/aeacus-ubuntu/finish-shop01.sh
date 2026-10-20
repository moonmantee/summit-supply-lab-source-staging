#!/usr/bin/env bash
# Re-prove reviewed scoring changes, then perform the approved encrypted cutover.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
bash "$source_dir/rehearse-all.sh"
bash "$source_dir/deploy-scoring.sh"
