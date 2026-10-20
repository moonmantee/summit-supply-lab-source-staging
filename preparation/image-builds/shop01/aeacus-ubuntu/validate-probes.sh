#!/usr/bin/env bash
# Read-only candidate validation. Does not replace the production scorer.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
candidate=$(mktemp -d /var/tmp/summit-shop01-validation-XXXXXXXX)
trap 'rm -rf -- "$candidate"' EXIT
install -d -m 700 "$candidate/package" "$candidate/engine"
cp -a "$source_dir/probes" "$candidate/package/"
for name in build_config.py competition-manifest.json validate_results.py test_build_config.py test_stage_common.py stage_common.sh; do
  install -m 600 "$source_dir/$name" "$candidate/package/$name"
done
chown -R root:root "$candidate"
find "$candidate" -type d -exec chmod 700 {} +
find "$candidate" -type f -exec chmod 600 {} +
python3 -m unittest discover -s "$candidate/package" -p 'test_*.py'
python3 -m unittest discover -s "$candidate/package/probes" -p 'test_*.py'
python3 "$candidate/package/build_config.py" --probe-root "$candidate/package" --output scoring.conf
cp -a /opt/aeacus/assets "$candidate/engine/"
install -m 600 "$candidate/package/scoring.conf" "$candidate/engine/scoring.conf"
printf '%s\n' ORGANIZER-VALIDATION > "$candidate/engine/TeamID.txt"
python3 "$candidate/package/validate_results.py" > "$candidate/before.json"
/opt/aeacus/aeacus --dir "$candidate/engine/" check
/opt/aeacus/aeacus --dir "$candidate/engine/" score
python3 "$candidate/package/validate_results.py" > "$candidate/after.json"
# Preserve non-secret diagnostics even when comparison fails. No observations,
# hashes or private configuration are included in these status-only files.
install -o jwang -g jwang -m 600 "$candidate/before.json" /home/jwang/shop01-probe-before.json
install -o jwang -g jwang -m 600 "$candidate/after.json" /home/jwang/shop01-probe-after.json
install -o jwang -g jwang -m 600 "$candidate/engine/assets/ScoringReport.html" /home/jwang/shop01-probe-validation-report.html
python3 - "$candidate" <<'PY'
import json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]); before=json.loads((root/'before.json').read_text()); after=json.loads((root/'after.json').read_text())
if before!=after:
    old={i['id']:i['status'] for i in before['checks']}
    changed=[f"{i['id']}: {old.get(i['id'])} -> {i['status']}" for i in after['checks'] if old.get(i['id'])!=i['status']]
    raise SystemExit('Probe states changed: '+', '.join(changed)+'. Status-only diagnostics saved in /home/jwang/shop01-probe-before.json and shop01-probe-after.json.')
html=(root/'engine/assets/ScoringReport.html').read_text()
score=re.search(r'(\d+) out of (\d+) points received',html)
actual=tuple(map(int,score.groups())) if score else None
assert actual==(after['expected_points'],100), f"Engine/probe mismatch: engine {actual}, expected {(after['expected_points'],100)}. Engine report and before/after JSON preserved in /home/jwang."
assert after['count']==40 and after['total_points']==100
for item in after['checks']: print('Objective %02d: %s' % (item['id'],item['status']))
print('Engine agrees: %d/100 across 40 objectives' % after['expected_points'])
print('ERROR states need investigation or missing fixture prerequisites; they are not repairs.')
PY
install -o jwang -g jwang -m 600 "$candidate/after.json" /home/jwang/shop01-probe-validation.json
install -o jwang -g jwang -m 600 "$candidate/engine/assets/ScoringReport.html" /home/jwang/shop01-probe-validation-report.html
echo 'Read-only validation complete. Production scorer unchanged; no weaknesses planted.'
