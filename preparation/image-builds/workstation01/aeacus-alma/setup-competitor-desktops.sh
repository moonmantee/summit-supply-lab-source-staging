#!/usr/bin/env bash
# Shared submissions and visible instructions/reports for approved competitors.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import json,os,pathlib,pwd,stat,subprocess,sys
sys.path.insert(0,'probes')
import scenario
def call(args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=40)
    if p.returncode:
        raise RuntimeError(args[0]+' failed\n'+p.stdout+p.stderr)
    return p.stdout.strip()
names=('alex.admin@corp.summit.test','taylor.admin@corp.summit.test','competitor-recovery')
root=pathlib.Path('/srv/summit-competition')
backup=pathlib.Path('/var/backups/summit-competitor-desktops')
assert not root.exists() and not root.is_symlink(),'Shared competition path already exists'
assert not backup.exists(),'Desktop migration already prepared'
group=call(['getent','group','linux-workstation-admins@corp.summit.test']).split(':')
assert len(group)==4,'Domain competitor group unavailable'
gid=int(group[2]); users={name:pwd.getpwnam(name) for name in names}
old=pathlib.Path('/home/jwang/Desktop/Forensics.txt')
assert old.is_file() and not old.is_symlink(),'Original forensic answer file missing'
original=old.read_bytes()
for name,user in users.items():
    home=pathlib.Path(user.pw_dir)
    assert str(home)=='/home/'+name,'Unexpected competitor home path'
    assert not home.is_symlink() and not (home/'Desktop').is_symlink(),'Symlink home/desktop'
    if home.exists():
        assert home.is_dir() and home.stat().st_uid==user.pw_uid,'Home ownership differs'
    for filename in ('Summit-Instructions.desktop','Summit-Report.desktop','Summit-Forensics.desktop'):
        path=home/'Desktop'/filename
        assert not path.exists() and not path.is_symlink(),'Desktop shortcut already exists'
backup.mkdir(mode=0o700)
call(['cp','-a',str(old),str(backup/'Forensics-original.txt')])
root.mkdir(mode=0o755)
answer=root/'Forensics.txt'; answer.write_bytes(original)
os.chown(answer,0,gid); answer.chmod(0o664)
# Fallback access uses its local UID, independent of domain group resolution.
call(['setfacl','-m','u:%d:rw-'%users['competitor-recovery'].pw_uid,str(answer)])
instructions=root/'Instructions.html'
instructions.write_bytes(pathlib.Path('competition-ReadMe.conf').read_bytes()); instructions.chmod(0o644)
report=root/'ScoringReport.html'
report.write_text('<h1>Practice image under construction</h1><p>The next validation run will publish its report here. Production scoring remains the organizer baseline.</p>\n'); report.chmod(0o644)
shortcuts={
 'Summit-Instructions.desktop':('Summit Instructions','firefox file:///srv/summit-competition/Instructions.html'),
 'Summit-Report.desktop':('Summit Practice Validation Report','firefox file:///srv/summit-competition/ScoringReport.html'),
 'Summit-Forensics.desktop':('Summit Forensic Answers','gedit /srv/summit-competition/Forensics.txt'),
}
for name,user in users.items():
    home=pathlib.Path(user.pw_dir)
    if not home.exists():
        home.mkdir(mode=0o700); os.chown(home,user.pw_uid,user.pw_gid)
    desktop=home/'Desktop'
    if not desktop.exists():
        desktop.mkdir(mode=0o700); os.chown(desktop,user.pw_uid,user.pw_gid)
    for filename,(title,command) in shortcuts.items():
        path=desktop/filename
        with path.open('x') as f:
            f.write('[Desktop Entry]\nType=Application\nName='+title+'\nExec='+command+'\nTerminal=false\n')
        path.chmod(0o755); os.chown(path,user.pw_uid,user.pw_gid)
    call(['restorecon','-R',str(home)])
call(['restorecon','-R',str(root)])
for name in names:
    # Verify actual user-context access, not root's ability to read/write.
    call(['runuser','-u',name,'--','test','-r',str(answer)])
    call(['runuser','-u',name,'--','test','-w',str(answer)])
    call(['runuser','-u',name,'--','test','-r',str(instructions)])
    call(['runuser','-u',name,'--','test','-r',str(report)])
    for filename in shortcuts:
        # Trusted metadata is cosmetic; some non-session environments do not
        # support gio metadata. The executable shortcut remains available.
        subprocess.run(['runuser','-u',name,'--','gio','set',str(pathlib.Path(users[name].pw_dir)/'Desktop'/filename),'metadata::trusted','true'],capture_output=True,timeout=15)
assert str(answer)==scenario.FORENSICS_FILE,'Probe submission path differs'
try:
    answer.write_text(''.join('Q%d = %s\n'%scenario.ANSWERS[i] for i in (17,18,19)))
    assert all(scenario.check(i) for i in (17,18,19)),'Shared correct answers did not score'
    answer.write_text('Q1 = incorrect\nQ2 = incorrect\nQ3 = incorrect\n')
    assert not any(scenario.check(i) for i in (17,18,19)),'Incorrect answers scored'
finally:
    answer.write_bytes(original)
assert answer.read_bytes()==original,'Original answers not restored'
(backup/'migration.json').write_text(json.dumps({'users':names,'shared_answers':str(answer),'read_write_verified':True,'forensic_rehearsal_passed':True},indent=2)+'\n')
(backup/'migration.json').chmod(0o600)
print('Both domain competitors and local fallback can read reports/instructions and edit shared forensic answers.')
print('Forensic positive/negative tests passed; original unanswered file restored.')
print('Desktop shortcuts created. Actual desktop launch and DC-outage access still need final rehearsal.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
