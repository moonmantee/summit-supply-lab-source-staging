#!/usr/bin/env bash
# Host-only sudo for an explicitly selected existing AD security group.
# Never creates or changes AD users/groups.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
python3 - <<'PY'
import json,pathlib,re,subprocess
def call(args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=45)
    if p.returncode:
        raise RuntimeError('Command failed: '+args[0]+'\n'+p.stdout+p.stderr)
    return p.stdout.strip()
group='Linux-Workstation-Admins@corp.summit.test'
members=('alex.admin@corp.summit.test','taylor.admin@corp.summit.test')
grant=pathlib.Path('/etc/sudoers.d/93-summit-domain-competitors')
backup=pathlib.Path('/var/backups/summit-domain-competitor-access')
assert not grant.exists() and not grant.is_symlink(),'Host sudo grant already exists'
assert not backup.exists(),'Host recovery record already exists'
# Fail before granting any rights if the approved group has not been created.
call(['getent','group',group])
for name in members:
    call(['getent','passwd',name])
# Populate entries before expiring them: sss_cache can otherwise reject a
# valid newly created identity that has not yet been looked up on this host.
call(['sss_cache','-g',group])
for name in members:
    call(['sss_cache','-u',name])
row=call(['getent','group',group]).split(':')
assert len(row)==4 and row[0].lower()==group.lower(),'Approved domain group does not resolve'
canonical=row[0]
assert re.fullmatch(r'[A-Za-z0-9_.@-]+',canonical),'Unsupported group spelling; do not interpolate unsafe sudo syntax'
for name in members:
    fields=call(['getent','passwd',name]).split(':')
    assert len(fields)==7 and fields[0].lower()==name.lower(),'Approved domain user does not resolve'
    groups=call(['id','-nG',name]).lower().split()
    assert canonical.lower() in groups,'Approved user not in selected admin group: '+name
call(['visudo','-c'])
original=call(['sudo','-n','-ll','-U','jwang'])
backup.mkdir(mode=0o700)
(backup/'jwang-before.txt').write_text(original+'\n'); (backup/'jwang-before.txt').chmod(0o600)
text='Defaults:%%%s authenticate,timestamp_timeout=5\n%%%s ALL=(ALL:ALL) PASSWD: ALL\n'%(canonical,canonical)
with grant.open('x') as f:
    f.write(text)
grant.chmod(0o440)
try:
    call(['visudo','-c'])
    for name in members:
        listing=call(['sudo','-n','-ll','-U',name])
        assert 'Sudoers entry:' in listing and 'Commands:' in listing and '!authenticate' not in listing,'Effective domain sudo differs from password-required policy'
    assert call(['sudo','-n','-ll','-U','jwang'])==original,'Organizer sudo policy changed'
except BaseException:
    assert not grant.is_symlink() and grant.read_text()==text,'Grant changed; refusing cleanup'
    grant.unlink()
    raise
(backup/'configured.json').write_text(json.dumps({'group':canonical,'verified_members':members,'password_required':True,'timeout_minutes':5},indent=2)+'\n')
(backup/'configured.json').chmod(0o600)
print('Domain competitor sudo configured for '+canonical+'.')
print('Both approved accounts resolve and require sudo authentication; jwang remains unchanged.')
print('Test an actual domain-user sudo session before release. This script does not change SSH policy or AD.')
PY
