"""Prepare inert organizer assets locally. Never install or run persistence."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

root=Path(__file__).parent
sys.path.insert(0,str(root/'probes'))
from scenario import PAYLOAD,HASH,ANSWERS

assets=root/'scenario-assets'
evidence=root/'evidence'
assets.mkdir(exist_ok=True)
evidence.mkdir(exist_ok=True)
files={
    'systemd-marker.sh':PAYLOAD,
    'cron-marker.sh':b'#!/bin/sh\n# SUMMIT-TRAINING-CRON-MARKER\nprintf "training marker\\n" >> /var/tmp/summit-training-cron.log\n',
    'fictional-credentials.txt':b'SUMMIT-TRAINING-CREDENTIALS\nFictional account: sample-employee\nFictional password: PracticeOnly-NotARealPassword\n',
    'summit-marker.service':b'[Unit]\nDescription=SUMMIT-TRAINING-SYSTEMD-MARKER\n[Service]\nType=oneshot\nExecStart=/usr/local/lib/summit-training/systemd-marker.sh\n',
    'summit-marker.timer':b'[Unit]\nDescription=SUMMIT-TRAINING-SYSTEMD-MARKER\n[Timer]\nOnBootSec=120\nOnUnitActiveSec=300\n[Install]\nWantedBy=timers.target\n',
    'summit-marker.cron':b'# SUMMIT-TRAINING-CRON-MARKER\n*/5 * * * * root /usr/local/lib/summit-training/cron-marker.sh\n',
    'Forensics.txt':b'Answer format: one Q<number> = value per line.\nQ1 = \nQ2 = \nQ3 = \n',
    'offline-game.py':b'#!/usr/bin/env python3\n# SUMMIT-TRAINING-OFFLINE-GAME\nimport random\nnumber=random.randint(1,10)\ntry:\n    guess=int(input("Guess a number from 1 to 10: "))\n    print("Correct!" if guess==number else "The answer was %d" % number)\nexcept (ValueError,EOFError):\n    print("Game ended.")\n',
    'summit-offline-game.desktop':b'[Desktop Entry]\nType=Application\nName=Summit Guessing Game\nComment=SUMMIT-TRAINING-OFFLINE-GAME\nExec=/usr/bin/python3 /usr/local/share/summit-games/offline-game.py\nTerminal=true\n',
    'app.conf':b'# Required Summit Supply training business configuration\nendpoint=https://portal.corp.summit.test\n',
    'summit-workstation.sh':b'# Required Summit Supply training environment\nexport SUMMIT_WORKSTATION_ROLE=employee\n',
}
for name,data in files.items():
    (assets/name).write_bytes(data)
with zipfile.ZipFile(assets/'personal-media.zip','w',compression=zipfile.ZIP_STORED) as archive:
    item=zipfile.ZipInfo('personal-media.txt',date_time=(2026,1,1,0,0,0))
    archive.writestr(item,b'SUMMIT-TRAINING-PERSONAL-MEDIA\nOriginal fictional personal media sample for competition practice.\n')
(evidence/'systemd-marker.sh').write_bytes(PAYLOAD)
(evidence/'scenario-events.txt').write_text('SYNTHETIC TRAINING EVIDENCE - NOT REAL SYSTEM LOGS\nactor=summit-contractor action=created-systemd-persistence\nunit=summit-marker.timer service=summit-marker.service\npayload=/usr/local/lib/summit-training/systemd-marker.sh\nsha256='+HASH+'\n')
inventory={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.iterdir() if p.is_file()}
(root/'artifact-hashes.json').write_text(json.dumps(inventory,indent=2)+'\n')
manifest=json.loads((root/'competition-manifest.json').read_text(encoding='utf-8-sig'))
targets={8:'summit-keyuser',20:'summit-admin',37:'summit-unknown',38:'summit-departed',39:'summit-employee',40:'summit-auditor'}
for issue in manifest['issues']:
    if issue['id'] in targets:
        issue['target_local_account']=targets[issue['id']]
manifest['required_recovery_account']='jwang'
manifest['domain']='corp.summit.test'
manifest['synthetic_ca_sha256']='27a1a39bd003d5fc0494e82066570ef74206d4da486c39d946faaba239ba5ebe'
manifest['artifact_hashes']=inventory
manifest['forensic_evidence_sha256']=HASH
(root/'competition-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Prepared %d inert scenario assets and separate forensic evidence. Nothing installed.'%len(inventory))
