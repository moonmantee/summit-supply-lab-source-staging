#!/usr/bin/env bash
# Privileged READ-ONLY validation; does not install scoring or plant weaknesses.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 -m unittest discover -s probes -p test_core.py
result=$(mktemp /home/jwang/.summit-core-validation.XXXXXX)
engine_dir=$(mktemp -d /var/tmp/summit-aeacus-validation.XXXXXX)
trap 'rm -f -- "$result"; rm -rf -- "$engine_dir"' EXIT
python3 probes/core.py --report > "$result"
chmod 600 "$result"
chown jwang:jwang "$result"
mv -- "$result" /home/jwang/summit-core-validation.json
python3 - <<'PY'
import json
d=json.load(open('/home/jwang/summit-core-validation.json'))
for issue,result in d.items():
    print('Issue %s: %s' % (issue, 'PASS' if result['pass'] else 'FAIL'))
print('Read-only scoring validation saved. No vulnerabilities planted.')
PY
cp -a /opt/aeacus/assets "$engine_dir/"
install -m 600 core-validation-scoring.conf "$engine_dir/scoring.conf"
printf '%s\n' 'ORGANIZER-VALIDATION' > "$engine_dir/TeamID.txt"
/opt/aeacus/aeacus --dir "$engine_dir/" --verbose check
/opt/aeacus/aeacus --dir "$engine_dir/" --verbose score
install -o jwang -g jwang -m 600 "$engine_dir/assets/ScoringReport.html" /home/jwang/summit-core-scoring-report.html
echo 'Isolated engine test complete; production baseline scorer was not changed.'
