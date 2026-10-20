"""Organizer-only real passwd/PAM rehearsal; never emit generated secrets."""
import json
import pathlib
import secrets
import subprocess
import sys

NORMAL='summit_pam_probe'
RECOVERY='summit_pam_recovery_probe'

def call(args,input=None):
    return subprocess.run(args,input=input,capture_output=True,text=True,timeout=15)

def initialize(user,password):
    p=call(['openssl','passwd','-6','-stdin'],password+'\n')
    assert p.returncode==0
    p=call(['chpasswd','-e'],user+':'+p.stdout.strip()+'\n')
    assert p.returncode==0
    assert call(['faillock','--user',user,'--reset']).returncode==0

def change(user,old,new,want,reason=None):
    p=call(['runuser','-u',user,'--','passwd'],old+'\n'+new+'\n'+new+'\n')
    assert (p.returncode==0)==want, 'Password change result disagrees with '+str(reason or 'acceptance')
    if not want:
        output=(p.stdout+p.stderr).lower()
        assert ('bad password' in output if reason=='quality' else 'used' in output), 'Policy rejection was not demonstrated'

def auth(user,password,want):
    p=call(['pamtester','login',user,'authenticate','acct_mgmt'],password+'\n')
    assert (p.returncode==0)==want, 'Actual PAM authentication result mismatch'

def verify(secure):
    current=secrets.token_urlsafe(24)
    initialize(NORMAL,current)
    # Thirteen mixed characters cannot meet the published fourteen minimum.
    short='A7!'+secrets.token_hex(5)
    change(NORMAL,current,short,not secure,'quality')
    if not secure: current=short
    poor='a'*20
    change(NORMAL,current,poor,not secure,'quality')
    if not secure: current=poor
    one=secrets.token_urlsafe(24); two=secrets.token_urlsafe(24)
    change(NORMAL,current,one,True)
    change(NORMAL,one,two,True)
    change(NORMAL,two,one,not secure,'history')
    current=two if secure else one
    for _ in range(3): auth(NORMAL,'intentionally-wrong-test-value',False)
    auth(NORMAL,current,True)  # success clears failures
    for _ in range(5): auth(NORMAL,'intentionally-wrong-test-value',False)
    auth(NORMAL,current,not secure)
    assert call(['faillock','--user',NORMAL,'--reset']).returncode==0
    auth(NORMAL,current,True)
    password=secrets.token_urlsafe(24)
    initialize(RECOVERY,password)
    for _ in range(5): auth(RECOVERY,'intentionally-wrong-test-value',False)
    auth(RECOVERY,password,True)  # sudo-group recovery remains exempt
    return {'minimum_rejection':secure,'quality_rejection':secure,
            'history_rejection':secure,'five_failure_lockout':secure,
            'success_resets_failures':True,'recovery_exempt':True}

if __name__=='__main__':
    phase=sys.argv[1]
    states=verify(phase=='secure')
    pathlib.Path(sys.argv[2]).write_text(json.dumps({'phase':phase,'functional':states})+'\n')
    print('Actual passwd/PAM '+phase+' behavior verified; generated secrets withheld.')
