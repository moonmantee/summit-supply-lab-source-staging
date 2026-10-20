#!/usr/bin/env bash
# Rehearse domain competitor sudo issues; stable fallback/organizer grants untouched.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import json,pathlib,subprocess,sys
sys.path.insert(0,'probes')
import access
def call(args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=45)
    if p.returncode:
        raise RuntimeError('Command failed: '+args[0]+'\n'+p.stdout+p.stderr)
    return p.stdout.strip()
group='linux-workstation-admins@corp.summit.test'
stable=pathlib.Path('/etc/sudoers.d/93-summit-domain-competitors')
fallback=pathlib.Path('/etc/sudoers.d/92-summit-competitor-recovery')
grant=pathlib.Path('/etc/sudoers.d/94-summit-domain-scenario')
backup=pathlib.Path('/var/backups/summit-domain-sudo-stage')
assert not backup.exists(),'Batch already prepared; refusing to replace recovery records'
assert not grant.exists() and not grant.is_symlink(),'Scenario override already exists'
assert stable.is_file() and not stable.is_symlink() and fallback.is_file() and not fallback.is_symlink(),'Stable competitor access is not prepared'
assert call(['getent','group',group]).split(':')[0].lower()==group,'Approved group does not resolve'
call(['visudo','-c'])
assert access.check(20) and access.check(21),'Clean domain sudo checks failed; no overrides created'
baseline_files={str(p):p.read_bytes() for p in (stable,fallback)}
baseline_listings={name:call(['sudo','-n','-ll','-U',name]) for name in ('jwang','competitor-recovery')}
assert all('Sudoers entry:' in value and '!authenticate' not in value for value in baseline_listings.values()),'Stable recovery authorization is unexpected'
backup.mkdir(mode=0o700)
for p in (stable,fallback):
    call(['cp','-a',str(p),str(backup/p.name)])
(backup/'stable-listings.json').write_text(json.dumps(baseline_listings,indent=2)+'\n')
(backup/'stable-listings.json').chmod(0o600)
weak='Defaults:%%%s timestamp_timeout=60\n%%%s ALL=(ALL:ALL) NOPASSWD: ALL\n'%(group,group)
created=False
def verify_stable():
    for name,value in baseline_listings.items():
        assert call(['sudo','-n','-ll','-U',name])==value,'Stable fallback/organizer sudo changed: '+name
    assert all(pathlib.Path(name).read_bytes()==value for name,value in baseline_files.items()),'Stable sudo file changed'
def plant():
    global created
    with grant.open('x') as f:
        f.write(weak)
    created=True
    grant.chmod(0o440)
    call(['visudo','-c']); verify_stable()
def clean():
    global created
    if created:
        assert not grant.is_symlink() and grant.read_text()==weak,'Scenario grant changed; refusing deletion'
        grant.unlink(); created=False
    call(['visudo','-c']); verify_stable()
def result():
    return {str(i):access.check(i) for i in (20,21)}
records={'clean':result()}
try:
    plant(); records['planted']=result()
    assert not any(records['planted'].values()),'Weak domain sudo policy falsely awarded points'
    clean(); records['repaired']=result()
    assert all(records['repaired'].values()),'Domain sudo repair failed'
    plant(); records['final_planted']=result()
    assert not any(records['final_planted'].values()),'Final weak domain policy falsely awarded points'
except BaseException:
    clean()
    raise
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
print('Issues 20, 21: clean PASS, planted FAIL, repaired PASS, final planted FAIL.')
print('Weak policy applies only to the domain competitor group. Local fallback and organizer sudo remain unchanged.')
print('AD membership, PAM, SSSD and SSH unchanged. No passwords collected.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
