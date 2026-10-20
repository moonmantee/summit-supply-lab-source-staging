"""Save current implementation status and a private organizer key locally."""
import json
from pathlib import Path
import sys

root=Path(__file__).parent
sys.path.insert(0,str(root/'probes'))
from scenario import ANSWERS
manifest=json.loads((root/'competition-manifest.json').read_text(encoding='utf-8-sig'))
staged={8,9,10,11,12,13,14,23,24,25,27,28,29,30,31,33,34,35,36,37,38,39,40}
forensics={17,18,19}
for issue in manifest['issues']:
    if issue['id'] in staged:
        issue['scenario_status']='planted-and-repair-rehearsed'
    elif issue['id'] in forensics:
        issue['scenario_status']='unanswered-positive-and-negative-answer-tests-verified'
    else:
        issue['scenario_status']='not-yet-staged-or-rehearsed'
    issue['implementation_status']='live-engine-validated'
(root/'competition-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
lines=['# Organizer answer key — workstation01 AlmaLinux','',
       'Private organizer master. Do not install this file on the participant desktop. The image is unfinished; do not advertise a completed 40-issue competition.', '',
       'Current milestone: 23 deliberate security issues staged, three forensic questions tested, isolated engine 10/100. Production remains the original three-check baseline. CORP desktop/business access unverified; sensitive changes held.', '',
       'All point checks have run through the live engine. This does not prove every remediation is complete: controlled authentication tests, actual employee desktop sessions, update-job execution, reboot persistence, full 100/100 solution, and snapshot recovery still remain.', '']
for issue in manifest['issues']:
    lines+=['## %d — %s (%d points)'%(issue['id'],issue['category'],issue['points']),'',
            'Starting issue: '+issue['planted_state'], '',
            'Required repair: '+issue['repair'], '',
            'Status: '+issue['scenario_status']+'.','']
    if issue['id'] in ANSWERS:
        number,value=ANSWERS[issue['id']]
        lines+=['Expected answer: `Q%d = %s`.'%(number,value),'']
lines+=['## Recovery records','',
        'Configuration archive: /var/backups/summit-workstation01-20261002T050048Z/configuration.tar.gz. User-confirmed snapshot; restore behavior not yet rehearsed.', '',
        'Guest root-only batch records: summit-application-stage, summit-persistence-stage, summit-trust-key-stage, summit-user-stage-retry1, summit-desktop-service-stage, and summit-software-stage-retry1 under /var/backups. Failed first-attempt records are retained. Inspect each original-state/rehearsal record before restoring anything.', '',
        'Signed software recovery masters: /var/backups/summit-package-recovery-retry1/inventory.json. Hash-check masters before use. DNF download paths are separate from archived masters because later transactions can delete tracked download-only files.', '',
        'No universal clean-state restoration script is yet certified. Avoid blanket deletion, account recreation, or restoring whole authentication directories over unrelated changes. Final release requires a complete solve/reboot/revert rehearsal.', '']
(root/'ORGANIZER-ANSWER-KEY.md').write_text('\n'.join(lines))
print('Saved private organizer key and status for 23 staged issues plus 3 forensic questions.')
