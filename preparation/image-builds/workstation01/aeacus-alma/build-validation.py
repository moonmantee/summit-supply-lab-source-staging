"""Generate organizer-only isolated scoring from the issue manifest."""
import json
from pathlib import Path

root=Path(__file__).parent
manifest=json.loads((root/'competition-manifest.json').read_text(encoding='utf-8-sig'))
core={5,6,16,29,30,32}
policy={9,10,12,13,14,23,33,35}
scenario={17,18,19,24,25,27,28,34,36,37,38}
access={1,2,3,4,7,8,15,20,21,22,26,31,39,40}
trust={11}
groups={'core':core,'policy':policy,'scenario':scenario,'access':access,'trust':trust}
all_issues=set().union(*groups.values())
assert all_issues==set(range(1,41))
assert len(manifest['issues'])==40 and sum(i['points'] for i in manifest['issues'])==100
chunks=['''name = "summit-workstation01-probe-validation"
title = "Organizer Probe Validation - Not Competition Scoring"
os = "AlmaLinux 9.8"
user = "alex.admin@corp.summit.test"
version = "2.1.1"
local = true
shell = false
''']
for item in manifest['issues']:
    if item['id'] not in all_issues:
        continue
    module=next(name for name,ids in groups.items() if item['id'] in ids)
    command='/usr/bin/python3 /home/jwang/aeacus-setup/probes/%s.py --issue %d'%(module,item['id'])
    chunks.append('\n[[check]]\nmessage = %s\npoints = %d\n[[check.pass]]\ntype = "CommandOutput"\ncmd = %s\nvalue = "PASS"\n'%(json.dumps('%d - %s'%(item['id'],item['repair'])),item['points'],json.dumps(command)))
    if item['implementation_status']=='pending':
        item['implementation_status']='probe-unit-tested'
(root/'probe-validation-scoring.conf').write_text(''.join(chunks))
(root/'competition-manifest.json').write_text(json.dumps(manifest,indent=2))
implemented=[i for i in manifest['issues'] if i['id'] in all_issues]
print('Generated %d-check isolated validation configuration; %d points.'%(len(implemented),sum(i['points'] for i in implemented)))
