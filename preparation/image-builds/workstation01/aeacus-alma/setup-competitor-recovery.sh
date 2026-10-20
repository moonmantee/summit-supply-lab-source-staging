#!/usr/bin/env bash
# Stable local competitor access; separate from organizer and scored weak grants.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import pathlib,subprocess,stat
from competitor_access import pending_recovery_account
name='competitor-recovery'
def lookup(args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=30)
    assert p.returncode in (0,2),'Identity lookup failed'
    return p
global_user=lookup(['getent','passwd',name])
local_user=lookup(['getent','-s','files','passwd',name])
local_group=lookup(['getent','-s','files','group',name])
home=pathlib.Path('/home/competitor-recovery')
grant=pathlib.Path('/etc/sudoers.d/92-summit-competitor-recovery')
assert not grant.exists() and not grant.is_symlink(),'Fallback sudo policy already installed; refusing repeat'
subprocess.run(['visudo','-c'],check=True)
if global_user.returncode==0:
    user=local_user.stdout.strip().split(':'); group=local_group.stdout.strip().split(':')
    assert local_user.returncode==0 and local_group.returncode==0 and len(user)==7 and len(group)==4 and global_user.stdout==local_user.stdout,'Existing identity is not the pending local fallback'
    assert home.is_dir() and not home.is_symlink(),'Pending home missing/unsafe'
    metadata=home.stat()
    groups=subprocess.run(['id','-nG',name],text=True,capture_output=True,timeout=30,check=True).stdout.split()
    state=dict(local=True,name=user[0],uid=int(user[2]),gid=int(user[3]),group_name=group[0],group_gid=int(group[2]),home=user[5],home_uid=metadata.st_uid,home_gid=metadata.st_gid,home_mode=stat.S_IMODE(metadata.st_mode),home_symlink=home.is_symlink(),shell=user[6],grant_absent=True,groups=groups)
    assert pending_recovery_account(state),'Existing fallback state differs; refusing modification'
    print('Resuming password setup for the existing noninteractive local fallback.')
else:
    global_group=lookup(['getent','group',name])
    assert local_user.returncode==2 and local_group.returncode==2 and global_group.returncode==2 and not home.exists() and not home.is_symlink(),'Existing account/group/home; refusing replacement'
    subprocess.run(['useradd','--create-home','--user-group','--shell','/sbin/nologin',name],check=True)
    print('Created local fallback account in noninteractive state.')
PY
printf '%s\n' 'Set the competitor fallback password locally below. Do not send it in chat.'
if ! passwd competitor-recovery; then
  printf '%s\n' 'Password setup did not complete. Account remains nologin; no sudo grant installed.'
  exit 1
fi
python3 - <<'PY'
import pathlib,pwd,spwd,subprocess
name='competitor-recovery'
entry=pwd.getpwnam(name); shadow=spwd.getspnam(name)
assert entry.pw_dir=='/home/competitor-recovery' and entry.pw_shell=='/sbin/nologin','Unexpected account state'
assert shadow.sp_pwdp and not shadow.sp_pwdp.startswith(('!','*')),'Local password is not active'
grant=pathlib.Path('/etc/sudoers.d/92-summit-competitor-recovery')
text='Defaults:competitor-recovery authenticate,timestamp_timeout=5\ncompetitor-recovery ALL=(ALL:ALL) PASSWD: ALL\n'
with grant.open('x') as f:
    f.write(text)
grant.chmod(0o440)
try:
    subprocess.run(['visudo','-c'],check=True)
    subprocess.run(['usermod','--expiredate','','--shell','/bin/bash',name],check=True)
    result=subprocess.run(['sudo','-n','-ll','-U',name],text=True,capture_output=True,timeout=30,check=True)
    assert 'Sudoers entry:' in result.stdout and 'Commands:' in result.stdout and '!authenticate' not in result.stdout,'Unexpected effective sudo policy'
    subprocess.run(['restorecon','-R','/home/competitor-recovery',str(grant)],check=True)
except BaseException:
    subprocess.run(['usermod','--shell','/sbin/nologin',name],check=True)
    assert not grant.is_symlink() and grant.read_text()==text,'Grant changed; refusing removal'
    grant.unlink()
    raise
print('Local competitor-recovery is ready with password-required sudo and a five-minute cache.')
print('Sign in using competitor-recovery, without a domain suffix, and test sudo -k followed by sudo -v.')
print('DC-outage login still needs a controlled rehearsal. jwang, CORP identities and scoring unchanged.')
PY
