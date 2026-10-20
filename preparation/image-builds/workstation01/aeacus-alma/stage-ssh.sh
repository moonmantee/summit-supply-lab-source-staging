#!/usr/bin/env bash
# Console-run SSH configuration rehearsal; restricted candidates are not loaded.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01 from the VM console.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import hashlib,json,os,pathlib,subprocess,sys
sys.path.insert(0,'probes')
import access,core
def call(args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=45)
    if p.returncode:
        raise RuntimeError('Command failed: '+args[0]+'\n'+p.stdout+p.stderr)
    return p.stdout.strip()
main=pathlib.Path('/etc/ssh/sshd_config')
backup=pathlib.Path('/var/backups/summit-ssh-stage-retry2')
previous_attempts=[pathlib.Path('/var/backups/summit-ssh-stage'),pathlib.Path('/var/backups/summit-ssh-stage-retry1')]
assert not backup.exists() and not backup.is_symlink(),'Recovery directory already exists; refusing replacement'
assert main.is_file() and not main.is_symlink() and main.stat().st_uid==0,'Unexpected SSH configuration'
assert main.stat().st_mode & 0o022==0,'SSH configuration is writable by non-root users'
original=main.read_bytes()
for previous in previous_attempts:
    if previous.exists():
        assert not (previous/'rehearsal.json').exists(),'Previous SSH stage completed; refusing duplicate staging'
        assert (previous/'sshd_config.original').read_bytes()==original,'Original SSH state from failed attempt is not restored'
call(['/usr/sbin/sshd','-t'])
assert call(['systemctl','is-active','sshd','sssd','summit-aeacus'])=='active\nactive\nactive','Required services unavailable'
contexts=[(user,addr) for user in access.SSH_USERS for addr in ('10.77.10.50','10.77.20.20')]
targets={'permitrootlogin','permitemptypasswords','allowgroups'}
def effective():
    outputs={}
    for user,addr in contexts:
        text=call(['/usr/sbin/sshd','-T','-C','user=%s,host=workstation01,addr=%s'%(user,addr)])
        outputs[user+'|'+addr]=access.ssh_output_rows(text)
    return outputs
baseline=effective()
for row in baseline.values():
    assert not any(row.get(k) for k in ('allowusers','allowgroups','denyusers','denygroups')),'Existing SSH roster requires separate review'
    assert row.get('pubkeyauthentication')==['yes'] and row.get('usepam')==['yes'],'Unexpected recovery authentication baseline'
for user in ('jwang','competitor-recovery')+access.COMPETITOR_ADMINS:
    assert set(call(['id','-nG',user]).split()) & access.SSH_GROUPS,'Approved SSH user lacks an approved group'
members=call(['getent','group','linux-workstation-admins@corp.summit.test']).split(':')[3].split(',')
assert set(members)==set(access.COMPETITOR_ADMINS),'Domain SSH group membership differs from approved roster'
backup.mkdir(mode=0o700)
call(['cp','-a',str(main),str(backup/'sshd_config.original')])
(backup/'effective-original.json').write_text(json.dumps(baseline,indent=2))
os.chmod(backup/'effective-original.json',0o600)
state={}
records=[]
current=original
def install():
    global current
    assert main.read_bytes()==current,'SSH file changed outside this rehearsal; refusing overwrite'
    prefix=''.join(key+' '+value+'\n' for key,value in state.items())
    candidate=prefix.encode()+original
    main.write_bytes(candidate)
    current=candidate
    call(['restorecon',str(main)])
    call(['/usr/sbin/sshd','-t'])
    actual=effective()
    for context,row in actual.items():
        assert {k:v for k,v in row.items() if k not in targets}=={k:v for k,v in baseline[context].items() if k not in targets},'Unrelated effective SSH settings changed'
    assert call(['systemctl','is-active','sssd','summit-aeacus'])=='active\nactive','Required services unavailable'
def passed(issue):
    return access.check(7) if issue==7 else core.evaluate(issue,core.collect(issue))
def record(issue,phase,expected):
    actual=passed(issue)
    if actual!=expected and issue==7:
        print(json.dumps({'ssh_roster_diagnostic':{context:{key:value for key,value in row.items() if key in ('allowgroups','allowusers','denyusers','denygroups')} for context,row in effective().items()}},indent=2),file=sys.stderr)
    assert actual==expected,'Issue %s %s expected %s got %s'%(issue,phase,expected,actual)
    records.append({'issue':issue,'phase':phase,'pass':actual})
try:
    # Rehearse each requirement separately. sshd -T evaluates on-disk candidates;
    # the live daemon retains its original access policy throughout these tests.
    for issue,key,good,bad in ((5,'PermitRootLogin','no','yes'),(6,'PermitEmptyPasswords','no','yes'),(7,'AllowGroups','jwang competitor-recovery linux-workstation-admins@corp.summit.test',None)):
        state[key]=good
        install(); record(issue,'clean',True)
        if bad is None: state.pop(key)
        else: state[key]=bad
        install(); record(issue,'planted',False)
        state[key]=good
        install(); record(issue,'repaired',True)
        if bad is None: state.pop(key)
        else: state[key]=bad
        install(); record(issue,'final-planted',False)
    assert all(not passed(issue) for issue in (5,6,7)),'Final candidate did not retain all three weaknesses'
    call(['systemctl','reload','sshd'])
    assert call(['systemctl','is-active','sshd'])=='active','SSH reload did not retain availability'
    (backup/'rehearsal.json').write_text(json.dumps({'tests':records,'final_config_sha256':hashlib.sha256(current).hexdigest(),'restricted_live_login_rehearsal':'pending'},indent=2))
    os.chmod(backup/'rehearsal.json',0o600)
except BaseException:
    if main.read_bytes()==current:
        main.write_bytes(original)
        call(['restorecon',str(main)])
        call(['/usr/sbin/sshd','-t'])
        call(['systemctl','reload','sshd'])
        print('SSH original configuration restored; recovery records retained.',file=sys.stderr)
    else:
        print('External configuration change detected; retained root backup for console recovery.',file=sys.stderr)
    raise
instructions=pathlib.Path('/srv/summit-competition/Instructions.html')
if instructions.is_file() and not instructions.is_symlink() and instructions.stat().st_uid==0:
    call(['cp','-a',str(instructions),str(backup/'Instructions.original.html')])
    call(['install','-o','root','-g','root','-m','644','competition-ReadMe.conf',str(instructions)])
print('Issues 5, 6, 7: configuration clean/planted/repaired/final checks passed separately.')
print('Final unrestricted scenario policy loaded. No account passwords, PAM, SSSD or sudo grants changed.')
print('Actual repaired-policy SSH login/denial and DC-outage fallback tests remain pending before release.')
PY
bash ./validate-probes.sh
