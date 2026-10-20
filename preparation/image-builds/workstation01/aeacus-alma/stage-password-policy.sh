#!/usr/bin/env bash
# Stock authselect local-policy rehearsal; execute from the VM console.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01 from the VM console.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import hashlib,json,os,pathlib,pwd,secrets,subprocess,sys
from auth_policy import update_policy,faillock_count
sys.path.insert(0,'probes')
import access
def call(args,input=None,secret=False):
    p=subprocess.run(args,input=input,text=True,capture_output=True,timeout=60,env=dict(os.environ,LC_ALL='C'))
    if p.returncode:
        raise RuntimeError('Command failed: '+args[0]+(' (secret-bearing output suppressed)' if secret else '\n'+p.stdout+p.stderr))
    return p.stdout.strip()
user='summit-policy-test'
backup=pathlib.Path('/var/backups/summit-password-policy-stage-retry1')
previous=pathlib.Path('/var/backups/summit-password-policy-stage')
runtime=pathlib.Path('/run/summit-password-policy-stage')
assert not backup.exists() and not backup.is_symlink(),'Policy recovery directory already exists; refusing replacement'
assert not runtime.exists() and not runtime.is_symlink(),'Rehearsal runtime already exists'
for kind in ('passwd','group'):
    p=subprocess.run(['getent',kind,user],text=True,capture_output=True)
    assert p.returncode==2 and not p.stdout,'Disposable identity/group exists or lookup failed'
original_profile=call(['authselect','current','-r']).split()
assert original_profile==['sssd','with-mkhomedir'],'Unexpected authselect profile/features; requires review'
call(['authselect','check'])
assert call(['systemctl','is-active','sshd','sssd','summit-aeacus'])=='active\nactive\nactive'
for name in access.COMPETITOR_ADMINS+('competitor-recovery','jwang'):
    pwd.getpwnam(name)
stable_sudo={name:call(['sudo','-n','-ll','-U',name]) for name in ('jwang','competitor-recovery')}
shadow=pathlib.Path('/etc/shadow')
shadow_original=shadow.read_bytes()
policies={name:pathlib.Path('/etc/security/'+name+'.conf') for name in ('pwquality','pwhistory','faillock')}
original={name:path.read_text() for name,path in policies.items()}
if previous.exists():
    assert not previous.is_symlink() and not (previous/'rehearsal.json').exists(),'Previous stage completed or recovery path unsafe'
    assert json.loads((previous/'authselect.original.json').read_text())==original_profile,'Original profile was not restored'
    for name,path in policies.items():
        assert path.read_bytes()==(previous/(name+'.conf.original')).read_bytes(),'Original policy was not restored: '+name
for path in policies.values():
    assert path.is_file() and not path.is_symlink() and path.stat().st_uid==0 and path.stat().st_mode & 0o022==0
backup.mkdir(mode=0o700)
for name,path in policies.items(): call(['cp','-a',str(path),str(backup/(name+'.conf.original'))])
history=pathlib.Path('/etc/security/opasswd')
assert not history.is_symlink(),'Unexpected history symlink'
if history.exists():
    assert not any(line.startswith((user+':').encode()) for line in history.read_bytes().splitlines()),'Disposable identity already has retained history; refusing replacement'
    call(['cp','-a',str(history),str(backup/'opasswd.original')])
(backup/'authselect.original.json').write_text(json.dumps(original_profile))
(backup/'authselect.original.json').chmod(0o600)
runtime.mkdir(mode=0o755)
runtime.chmod(0o755)
runner=runtime/'pam_runner.py'
call(['install','-o','root','-g','root','-m','644','pam_runner.py',str(runner)])
call(['restorecon','-R',str(runtime)])
created=False; success=False; records=[]; policy_changed=False
current=secrets.token_urlsafe(24)
def pam(operation,new=None,password=None):
    request={'user':user,'operation':operation,'current':current if password is None else password}
    if new is not None: request['new']=new
    args=['/usr/bin/python3',str(runner)]
    value=json.loads(call(args,json.dumps(request),secret=True))
    assert set(value)=={'pam_code'} and isinstance(value['pam_code'],int),'Invalid PAM runner result'
    return value['pam_code']
def change(new,accept,label):
    global current
    code=pam('change',new=new)
    if accept:
        assert code==0,label+' should accept; PAM code '+str(code)
        current=new
        assert pam('authenticate')==0,'Accepted password cannot authenticate'
    else:
        assert code in (11,20),label+' should reject by policy; PAM code '+str(code)
        assert pam('authenticate')==0,'Rejected change altered the current working password'
    records.append({'test':label,'accepted':accept,'pam_code':code})
    print(label+': PASS',flush=True)
quality={'minlen':'14','enforcing':'1','dcredit':'0','ucredit':'0','lcredit':'0','ocredit':'0','dictcheck':'1','usercheck':'1','retry':'1','local_users_only':None}
remember={'remember':'5','retry':'1'}
lockout={'deny':'5','fail_interval':'900','unlock_time':'900','local_users_only':None}
managed_current=dict(original)
def apply(name,values):
    global policy_changed
    path=policies[name]
    assert path.read_text()==managed_current[name],'Policy changed outside this rehearsal'
    contents=update_policy(original[name],values)
    path.write_text(contents); managed_current[name]=contents; policy_changed=True
    call(['restorecon',str(path)])
    call(['authselect','check'])
    assert call(['systemctl','is-active','sshd','sssd','summit-aeacus'])=='active\nactive\nactive'
    for name,text in stable_sudo.items():
        assert call(['sudo','-n','-ll','-U',name])==text,'Recovery sudo authorization changed'
def score(issue,expected,label):
    assert access.check(issue)==expected,'Issue %d %s scoring mismatch'%(issue,label)
    records.append({'issue':issue,'phase':label,'pass':expected})
def reset(): call(['faillock','--user',user,'--reset'])
def tally_count(): return faillock_count(call(['faillock','--user',user]),user)
def lock_test(enabled,label):
    reset()
    assert tally_count()==0,'Disposable failures were not reset'
    assert pam('authenticate')==0,'Initial disposable login failed'
    for number in range(1,5):
        assert pam('authenticate',password='incorrect-'+secrets.token_hex(12))==7,'Incorrect password did not produce authentication rejection'
        assert tally_count()==number,'PAM rejected a password without recording the expected failure'
    # Four failures must not lock an account whose threshold is five.
    assert pam('authenticate')==0,'Disposable account locked before five failures'
    assert tally_count()==0,'Successful login did not clear earlier failures'
    for number in range(1,6):
        assert pam('authenticate',password='incorrect-'+secrets.token_hex(12))==7
        assert tally_count()==number,'PAM rejected a password without recording the expected failure'
    print(label+': five recorded failures verified',flush=True)
    code=pam('authenticate')
    assert code==(7 if enabled else 0),label+' lockout behavior mismatch, PAM code '+str(code)
    reset()
    assert tally_count()==0
    assert pam('authenticate')==0,'Disposable account did not recover after scoped reset'
    records.append({'test':label,'lockout_after_five':enabled})
    print(label+': PASS',flush=True)
try:
    call(['useradd','-M','-d','/nonexistent','-s','/bin/bash',user]); created=True
    call(['chpasswd'],user+':'+current+'\n',secret=True)
    assert pam('authenticate')==0,'Baseline disposable PAM login failed; no policy mutation performed'
    change(secrets.token_urlsafe(24),True,'Baseline real-UID password change')
    # Configure the local-only scope BEFORE enabling faillock, so domain users
    # never pass through an interim locally tracked lockout configuration.
    apply('faillock',lockout); apply('pwhistory',remember); apply('pwquality',quality)
    call(['authselect','enable-feature','with-pwhistory'])
    call(['authselect','enable-feature','with-faillock'])
    call(['authselect','check'])
    for issue in (1,2,3,4): score(issue,True,'clean')
    # Exercise lockout first, so any harness problem aborts before the longer
    # password-change/history rehearsal. Each rejected password must be tallied.
    lock_test(True,'Clean local-only lockout')
    lockout['deny']='0'; apply('faillock',lockout); score(3,False,'planted')
    lock_test(False,'Weak local lockout is disabled')
    lockout['deny']='5'; apply('faillock',lockout); score(3,True,'repaired')
    lock_test(True,'Repaired local-only lockout')
    lockout['deny']='0'; apply('faillock',lockout); score(3,False,'final-planted')
    change('r9K!v2P@x7Q#z',False,'Clean minimum length rejects 13 characters')
    quality['minlen']='8'; apply('pwquality',quality); score(1,False,'planted')
    change('r9K!v2P@x7Q#z',True,'Weak minimum length accepts 13 characters')
    change(secrets.token_urlsafe(24),True,'Restore distinct strong disposable password')
    quality['minlen']='14'; apply('pwquality',quality); score(1,True,'repaired')
    change('r9K!v2P@x7Q#z',False,'Repaired minimum length rejects 13 characters')
    quality['minlen']='8'; apply('pwquality',quality); score(1,False,'final-planted')
    change('password',False,'Clean quality rejects dictionary password')
    quality['enforcing']='0'; apply('pwquality',quality); score(2,False,'planted')
    change('password',True,'Weak quality accepts dictionary password')
    change(secrets.token_urlsafe(24),True,'Restore distinct strong disposable password after quality test')
    quality['enforcing']='1'; apply('pwquality',quality); score(2,True,'repaired')
    change('password',False,'Repaired quality rejects dictionary password')
    quality['enforcing']='0'; apply('pwquality',quality); score(2,False,'final-planted')
    previous=[]
    for _ in range(6):
        previous.append(current)
        change(secrets.token_urlsafe(24),True,'Populate local history')
    change(previous[-3],False,'Clean history rejects a recent password')
    remember['remember']='0'; apply('pwhistory',remember); score(4,False,'planted')
    change(previous[-3],True,'Weak history accepts a recent password')
    remember['remember']='5'; apply('pwhistory',remember); score(4,True,'repaired')
    saved=current
    change(secrets.token_urlsafe(24),True,'Populate repaired local history')
    change(saved,False,'Repaired history rejects a recent password')
    remember['remember']='0'; apply('pwhistory',remember); score(4,False,'final-planted')
    assert not any(access.check(issue) for issue in (1,2,3,4))
    success=True
except BaseException as error:
    (backup/'failure.json').write_text(json.dumps({'error':str(error),'tests':records},indent=2)+'\n')
    (backup/'failure.json').chmod(0o600)
    raise
finally:
    if not success:
        for name,path in policies.items():
            if path.read_text()!=managed_current[name]: raise RuntimeError('External policy change; root recovery records retained for console repair')
        # Remove the new modules before restoring original scope/defaults.
        call(['authselect','select']+original_profile)
        for name,path in policies.items():
            call(['cp','-a',str(backup/(name+'.conf.original')),str(path)])
        call(['authselect','check'])
        print('Original local policies/authselect restored; recovery records retained.',flush=True)
    if created:
        reset()
        call(['usermod','-L','-s','/sbin/nologin',user])
        testuid=pwd.getpwnam(user).pw_uid
        if history.exists():
            lines=history.read_bytes().splitlines(keepends=True)
            for line in lines:
                if line.startswith((user+':').encode()):
                    assert line.split(b':')[1]==str(testuid).encode(),'Unexpected disposable history identity'
            history.write_bytes(b''.join(line for line in lines if not line.startswith((user+':').encode())))
        call(['userdel',user])
        tally=pathlib.Path(access.settings([policies['faillock'].read_text()]).get('dir','/var/run/faillock'))/user
        if tally.exists():
            assert not tally.is_symlink() and tally.is_file() and tally.stat().st_uid in (0,testuid) and tally.stat().st_size==0,'Unexpected disposable tally after reset; refusing removal'
            tally.unlink()
    assert shadow.read_bytes()==shadow_original,'Non-disposable account shadow state changed during rehearsal'
    # Runtime contains only the runner, never passwords. Remove that exact file.
    runner.unlink(); runtime.rmdir()
if success:
    (backup/'rehearsal.json').write_text(json.dumps({'tests':records,'real_passwords_unchanged':True,'domain_interactive_test':'pending','timed_unlock_test':'pending'},indent=2)+'\n')
    (backup/'rehearsal.json').chmod(0o600)
    print('Issues 1–4 planted; real PAM clean/planted/repaired tests passed. Disposable account removed.')
    print('SSSD and with-mkhomedir retained. Verify actual CORP and local fallback login/sudo next.')
PY
bash ./validate-probes.sh
