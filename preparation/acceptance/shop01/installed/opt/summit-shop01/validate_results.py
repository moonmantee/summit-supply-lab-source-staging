"""Collect only probe status tokens; no raw observations or secrets."""
import json
import subprocess
import sys
from pathlib import Path

def collect(root):
    manifest=json.loads((root/'competition-manifest.json').read_text())
    states=[]
    for item in manifest['issues']:
        p=subprocess.run(['/usr/bin/python3',str(root/'probes/check.py'),str(item['id'])],
                         text=True,capture_output=True,timeout=55)
        token=p.stdout.strip()
        if token not in ('PASS','FAIL','ERROR') or (p.returncode!=0 and token!='ERROR'):
            token='ERROR'
        states.append({'id':item['id'],'points':item['points'],'status':token})
    return {'checks':states,'expected_points':sum(i['points'] for i in states if i['status']=='PASS'),
            'total_points':sum(i['points'] for i in states),'count':len(states)}

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    print(json.dumps(collect(root),indent=2))
