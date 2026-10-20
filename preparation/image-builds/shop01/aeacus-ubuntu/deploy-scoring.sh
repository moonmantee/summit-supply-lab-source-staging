#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
private_source=$(mktemp -d /var/backups/summit-shop01-deploy-source-XXXXXXXX)
cp -a "$source_dir/." "$private_source/"
chown -R root:root "$private_source"
find "$private_source" -type d -exec chmod 700 {} +
find "$private_source" -type f -exec chmod 600 {} +
python3 -m unittest discover -s "$private_source" -p 'test_*.py'
python3 -m unittest discover -s "$private_source/probes" -p 'test_*.py'
python3 "$private_source/deploy-scoring.py"
