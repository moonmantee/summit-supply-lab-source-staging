#!/usr/bin/env bash
# Synthetic local identities only. Never modifies jwang or CORP identities.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import crypt,datetime,grp,json,os,pathlib,pwd,secrets,spwd,subprocess,sys
sys.path.insert(0,'probes')
import access,scenario
def call(args,input=None):
    return subprocess.run(args,input=input,text=True,capture_output=True,timeout=30,check=True)
names=('summit-unknown','summit-departed','summit-employee','summit-auditor')
backup=pathlib.Path('/var/backups/summit-user-stage-retry1')
grant=pathlib.Path('/etc/sudoers.d/90-summit-training-auditor')
assert not backup.exists(),'User batch already prepared; original state would be overwritten'
assert not grant.exists() and not grant.is_symlink(),'Sudo grant path already exists'
baseline={}
for name in names:
    local=call(['getent','-s','files','passwd',name]).stdout.strip().split(':')
    user=pwd.getpwnam(name); shadow=spwd.getspnam(name)
    assert len(local)==7 and local[0]==name and user.pw_uid>=1000,'Target is not a prepared local training account'
    assert local[6] in ('/sbin/nologin','/usr/sbin/nologin'),'Training account unexpectedly interactive'
    assert shadow.sp_pwdp.startswith(('!','*')) and shadow.sp_expire>=0,'Training account not initially locked/expired'
    groups=[g.gr_name for g in grp.getgrall() if name in g.gr_mem]
    assert 'wheel' not in groups,'Training account already has wheel privileges'
    baseline[name]={'hash':shadow.sp_pwdp,'expire':shadow.sp_expire,'shell':user.pw_shell,'groups':groups}
assert scenario.check(37) and scenario.check(38),'Initial disabled-account probes failed'
call(['visudo','-c'])
backup.mkdir(mode=0o700)
(backup/'original-accounts.json').write_text(json.dumps(baseline,indent=2)+'\n')
(backup/'original-accounts.json').chmod(0o600)
# Independent random valid passwords; never printed, never saved in plaintext.
# Their hashes stay only in shadow and the protected organizer recovery state.
hashes={name:crypt.crypt(secrets.token_urlsafe(32),crypt.mksalt(crypt.METHOD_SHA512)) for name in names}
assert all(value and value.startswith('$6$') for value in hashes.values()),'Password hashing unavailable'
def enable(name):
    call(['chpasswd','--encrypted'],name+':'+hashes[name]+'\n')
    call(['usermod','--expiredate','','--shell','/bin/bash',name])
def disable(name):
    call(['passwd','--lock',name])
    call(['usermod','--expiredate','1970-01-02','--shell','/sbin/nologin',name])
def no_admin():
    for name in ('summit-employee','summit-auditor'):
        if 'wheel' in call(['id','-nG',name]).stdout.split():
            call(['gpasswd','--delete',name,'wheel'])
    if grant.exists():
        assert not grant.is_symlink() and grant.read_text()==grant_text,'Changed sudo grant; refusing deletion'
        grant.unlink()
    call(['visudo','-c'])
grant_text='summit-auditor ALL=(ALL) ALL\n'
def clean():
    disable('summit-unknown'); disable('summit-departed')
    enable('summit-employee'); enable('summit-auditor')
    no_admin()
def plant():
    enable('summit-unknown'); enable('summit-departed')
    call(['usermod','--append','--groups','wheel','summit-employee'])
    with grant.open('x') as f:
        f.write(grant_text)
    grant.chmod(0o440)
    call(['visudo','-c'])
def result():
    return {'37':scenario.check(37),'38':scenario.check(38),'39':access.check(39),'40':access.check(40)}
def restore_original():
    no_admin()
    for name,data in baseline.items():
        call(['chpasswd','--encrypted'],name+':'+data['hash']+'\n')
        expiry='' if data['expire']<0 else str(datetime.date(1970,1,1)+datetime.timedelta(days=data['expire']))
        call(['usermod','--expiredate',expiry,'--shell',data['shell'],'--groups',','.join(data['groups']),name])
records={}
try:
    clean(); records['clean']=result()
    if not all(records['clean'].values()):
        # Sanitized authorization output makes any conservative-probe mismatch
        # diagnosable; password hashes and generated passwords are never printed.
        for name in ('summit-employee','summit-auditor'):
            p=subprocess.run(['sudo','-n','-ll','-U',name],text=True,capture_output=True,timeout=30)
            print('Authorization diagnostic for '+name+': exit '+str(p.returncode))
            print(p.stdout+p.stderr)
        raise AssertionError('Clean account/authorization checks failed; original states restored')
    plant(); records['planted']=result()
    assert not any(records['planted'].values()),'Planted user/privilege issue falsely passed'
    clean(); records['repaired']=result()
    assert all(records['repaired'].values()),'Repair checks failed'
    restore_original(); records['original_disabled']={'37':scenario.check(37),'38':scenario.check(38)}
    assert all(records['original_disabled'].values()),'Original disabled states did not restore'
    clean(); plant(); records['final_planted']=result()
    assert not any(records['final_planted'].values()),'Final planted check falsely passed'
except BaseException:
    restore_original()
    raise
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
assert pathlib.Path('/home/summit-departed').is_dir(),'Departed employee data directory lost'
print('Issues 37-40: clean PASS, planted FAIL, repaired PASS, original disabled states restored, final planted FAIL.')
print('Synthetic accounts only; random passwords not disclosed. jwang and CORP identities unchanged.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
