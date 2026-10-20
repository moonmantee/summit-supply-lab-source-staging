#!/usr/bin/env bash
# Read-only validation; leaves the installed baseline scorer unchanged.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 -m unittest discover -s probes -p 'test_*.py'
engine_dir=$(mktemp -d /var/tmp/summit-aeacus-validation.XXXXXX)
result=$(mktemp /home/jwang/.summit-probe-validation.XXXXXX)
trap 'rm -f -- "$result"; rm -rf -- "$engine_dir"' EXIT
python3 - <<'PY' > "$result"
import json,sys
sys.path.insert(0,'probes')
import core,policy,scenario,access,trust
data={str(i):{'pass':core.evaluate(i,observed),'observed':observed} for i in core.ISSUES for observed in [core.collect(i)]}
data.update({str(i):{'pass':policy.check(i)} for i in policy.ISSUES})
data.update({str(i):{'pass':scenario.check(i)} for i in scenario.ISSUES})
data.update({str(i):{'pass':access.check(i)} for i in access.ISSUES})
data.update({str(i):{'pass':trust.check(i)} for i in trust.ISSUES})
print(json.dumps(data,indent=2))
PY
chmod 600 "$result"
chown jwang:jwang "$result"
mv -- "$result" /home/jwang/summit-probe-validation.json
cp -a /opt/aeacus/assets "$engine_dir/"
install -m 600 probe-validation-scoring.conf "$engine_dir/scoring.conf"
printf '%s\n' 'ORGANIZER-VALIDATION' > "$engine_dir/TeamID.txt"
/opt/aeacus/aeacus --dir "$engine_dir/" --verbose check
/opt/aeacus/aeacus --dir "$engine_dir/" --verbose score
install -o jwang -g jwang -m 600 "$engine_dir/assets/ScoringReport.html" /home/jwang/summit-probe-scoring-report.html
if [[ -d /srv/summit-competition ]]; then
  install -o root -g root -m 644 "$engine_dir/assets/ScoringReport.html" /srv/summit-competition/ScoringReport.html
fi
python3 - <<'PY'
import json,re,pathlib
d=json.loads(pathlib.Path('/home/jwang/summit-probe-validation.json').read_text())
manifest=json.loads(pathlib.Path('competition-manifest.json').read_text())
points={str(i['id']):i['points'] for i in manifest['issues']}
expected=sum(points[i] for i,r in d.items() if r['pass'])
total=sum(points[i] for i in d)
html=pathlib.Path('/home/jwang/summit-probe-scoring-report.html').read_text()
actual=re.search(r'(\d+) out of (\d+) points received',html)
assert actual and tuple(map(int,actual.groups()))==(expected,total), 'Engine/probe score mismatch'
for i,r in sorted(d.items(),key=lambda x:int(x[0])):
    print('Issue %s: %s'%(i,'PASS' if r['pass'] else 'FAIL'))
print('Engine agrees with probes: %d/%d across %d checks'%(expected,total,len(d)))
print('Validation made no changes to vulnerabilities; production scorer unchanged.')
PY
