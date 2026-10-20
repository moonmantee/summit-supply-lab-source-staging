#!/usr/bin/env python3
"""Export only failure diagnostics and rollback receipt; never mutate system policy."""
import json,os,pathlib,pwd,re,socket
if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='sql01':
    raise SystemExit('Run with sudo on SQL01 only.')
record=pathlib.Path('/var/backups/summit-sql01-competition-9e81rcxw')
if record.is_symlink() or record.stat().st_uid!=0 or record.stat().st_mode & 0o077:
    raise SystemExit('Unexpected recovery record ownership/permissions.')
state=json.loads((record/'state.json').read_text())
diagnostics={'record':str(record),'phase':state.get('phase'),'failure':(record/'failure.txt').read_text(),
             'rollback_failure':(record/'rollback-failure.txt').read_text() if (record/'rollback-failure.txt').exists() else None,
             'failed_commands':[]}
lines=(record/'commands.log').read_text().splitlines()
for i,line in enumerate(lines):
    match=re.fullmatch(r'([^ ]+) exit=(\d+)',line)
    if not match or match[2]=='0': continue
    output=[]
    for following in lines[i+1:]:
        if re.fullmatch(r'([^ ]+) exit=(\d+)',following): break
        output.append(following)
    diagnostics['failed_commands'].append({'command':match[1],'exit_code':int(match[2]),'output':'\n'.join(output)})
text=json.dumps(diagnostics,indent=2)+'\n'
out=pathlib.Path('/home/jwang/sql01-failed-build-diagnostics.json')
fd=os.open(out,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as f: f.write(text)
user=pwd.getpwnam('jwang'); os.chown(out,user.pw_uid,user.pw_gid)
print(text)
print('Diagnostics saved: '+str(out))
