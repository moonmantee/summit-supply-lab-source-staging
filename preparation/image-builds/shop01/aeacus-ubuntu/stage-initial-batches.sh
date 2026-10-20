#!/usr/bin/env bash
# Run two independently reversible approved batches in sequence.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
bash "$source_dir/stage-persistence.sh"
bash "$source_dir/stage-permissions.sh"
echo 'Eight objectives staged and rehearsed: 25–29 and 38–40. Candidate score evidence updated.'
echo 'Production scoring remains unchanged pending full scenario validation.'
