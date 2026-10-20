#!/usr/bin/env bash
# Synthetic administrator authentication and scoped recovery-user cache timeout.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import crypt,datetime,json,pathlib,pwd,secrets,spwd,subprocess,sys
sys.path.insert(0,'probes')
import access
def call(args,input=None):
    p=subprocess.run(args,input=input,text=True,capture_output=True,timeout=30)
    if p.returncode:
        # This workflow never passes credentials on a command line.
        raise RuntimeError('Command failed: '+args[0]+'\n'+p.stdout+p.stderr)
    return p
target='summit-admin'
grant=pathlib.Path('/etc/sudoers.d/91-summit-training-admin')
backup=pathlib.Path('/var/backups/summit-sudo-stage')
assert not backup.exists(),'Batch already prepared; refusing replacement'
assert not grant.exists() and not grant.is_symlink(),'Scenario sudo policy exists'
user=pwd.getpwnam(target); shadow=spwd.getspnam(target)
local=call(['getent','-s','files','passwd',target]).stdout.strip().split(':')
assert len(local)==7 and local[0]==target and user.pw_uid>=1000,'Target must be a local training identity'
assert user.pw_shell in ('/sbin/nologin','/usr/sbin/nologin') and shadow.sp_pwdp.startswith(('!','*')) and shadow.sp_expire>=0,'Unexpected training-admin state'
call(['visudo','-c'])
before=call(['sudo','-n','-ll','-U','jwang']).stdout
assert 'Sudoers entry:' in before and 'Commands:' in before and 'ALL' in before,'Recovery administrator rights unavailable'
assert '!authenticate' not in before,'Recovery administrator already has password bypass; investigate first'
baseline={'hash':shadow.sp_pwdp,'expire':shadow.sp_expire,'shell':user.pw_shell}
backup.mkdir(mode=0o700)
(backup/'original-admin.json').write_text(json.dumps(baseline,indent=2)+'\n')
(backup/'original-admin.json').chmod(0o600)
(backup/'original-jwang-sudo.txt').write_text(before)
(backup/'original-jwang-sudo.txt').chmod(0o600)
password_hash=crypt.crypt(secrets.token_urlsafe(32),crypt.mksalt(crypt.METHOD_SHA512))
assert password_hash and password_hash.startswith('$6$'),'Password hashing unavailable'
created=False
known_texts=set()
def policy(protected):
    global created
    text='Defaults:jwang timestamp_timeout=%d\n'% (5 if protected else 60)
    text+='summit-admin ALL=(ALL) '+('ALL\n' if protected else 'NOPASSWD: ALL\n')
    if not created:
        with grant.open('x') as f:
            f.write(text)
        created=True
    else:
        assert not grant.is_symlink() and grant.read_text() in known_texts,'Scenario policy changed externally'
        grant.write_text(text)
    known_texts.add(text)
    grant.chmod(0o440)
    call(['visudo','-c'])
    recovery=call(['sudo','-n','-ll','-U','jwang']).stdout
    assert 'Sudoers entry:' in recovery and 'ALL' in recovery and '!authenticate' not in recovery,'Recovery administrator access altered'
def result():
    return {str(i):access.check(i) for i in (20,21)}
def restore_original():
    global created
    if created:
        assert not grant.is_symlink() and grant.read_text() in known_texts,'Changed sudo policy; refusing deletion'
        grant.unlink(); created=False
    call(['chpasswd','--encrypted'],target+':'+baseline['hash']+'\n')
    expiry='' if baseline['expire']<0 else str(datetime.date(1970,1,1)+datetime.timedelta(days=baseline['expire']))
    call(['usermod','--expiredate',expiry,'--shell',baseline['shell'],target])
    call(['visudo','-c'])
records={}
try:
    call(['chpasswd','--encrypted'],target+':'+password_hash+'\n')
    call(['usermod','--expiredate','','--shell','/bin/bash',target])
    policy(True); records['clean']=result()
    assert all(records['clean'].values()),'Authenticated administration/cache checks did not pass'
    policy(False); records['planted']=result()
    assert not any(records['planted'].values()),'Weak sudo policy falsely earned points'
    policy(True); records['repaired']=result()
    assert all(records['repaired'].values()),'Sudo repair checks failed'
    restore_original()
    assert call(['sudo','-n','-ll','-U','jwang']).stdout==before,'Original recovery-user policy did not restore'
    call(['chpasswd','--encrypted'],target+':'+password_hash+'\n')
    call(['usermod','--expiredate','','--shell','/bin/bash',target])
    policy(False); records['final_planted']=result()
    assert not any(records['final_planted'].values()),'Final sudo policy falsely earned points'
except BaseException:
    restore_original()
    raise
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
print('Issues 20, 21: clean PASS, planted FAIL, repaired PASS, original policy restored, final planted FAIL.')
print('jwang retains authenticated sudo authorization. Only its cache timeout changed; CORP/PAM/SSH untouched.')
print('Training-admin random password was not printed or stored in plaintext.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
