"""Generate exact Aeacus checks from the organizer manifest."""
import argparse
import json
import re
from pathlib import Path

FOUR_POINTS = {2,5,14,17,18,25,26,27,28,32}

def validate_manifest(data):
    issues = data.get('issues')
    if not isinstance(issues, list) or len(issues) != 40:
        raise ValueError('Exactly forty objectives are required')
    if [i.get('id') for i in issues] != list(range(1,41)):
        raise ValueError('IDs must be ordered, unique and complete')
    for i in issues:
        if type(i.get('id')) is not int or type(i.get('points')) is not int:
            raise ValueError('IDs and points must be integers')
        if i['points'] != (4 if i['id'] in FOUR_POINTS else 2):
            raise ValueError('Incorrect approved point allocation')
        if i.get('probe') != str(i['id']):
            raise ValueError('Probe must be the exact numeric objective identifier')
        if not isinstance(i.get('message'), str) or not i['message'].strip():
            raise ValueError('Missing score message')
    if sum(i['points'] for i in issues) != 100:
        raise ValueError('Score must total 100')
    return issues

def render(data, probe_root='/opt/summit-shop01'):
    issues = validate_manifest(data)
    if not re.fullmatch(r'/[A-Za-z0-9_/-]+', probe_root) or '..' in probe_root.split('/'):
        raise ValueError('Unsafe probe root')
    chunks = ['name = "summit-shop01-competition"\ntitle = "Summit Supply Ubuntu Security"\n'
              'os = "Ubuntu 24.04 LTS"\nuser = "jwang"\nversion = "2.1.1"\nlocal = true\nshell = false\n']
    for i in issues:
        cmd = f'/usr/bin/python3 {probe_root}/probes/check.py {i["id"]}'
        chunks.append(f'\n[[check]]\nmessage = {json.dumps(i["message"])}\npoints = {i["points"]}\n'
                      f'[[check.pass]]\ntype = "CommandOutput"\ncmd = {json.dumps(cmd)}\nvalue = "PASS"\n')
    return ''.join(chunks)

def main():
    p = argparse.ArgumentParser(); p.add_argument('--probe-root', default='/opt/summit-shop01')
    p.add_argument('--output', default='scoring.conf'); args = p.parse_args()
    base = Path(__file__).resolve().parent
    data = json.loads((base/'competition-manifest.json').read_text())
    output = base/args.output
    output.write_text(render(data, args.probe_root), encoding='utf-8', newline='\n')
    print('Generated forty checks / 100 points:', output)

if __name__ == '__main__': main()
