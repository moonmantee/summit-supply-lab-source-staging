#!/usr/bin/env bash
# Replace the shared sheet with independently scored question/answer documents.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import json,os,pathlib,pwd,subprocess,sys
sys.path.insert(0,'probes')
import scenario
def call(args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=40)
    if p.returncode: raise RuntimeError(args[0]+' failed\n'+p.stdout+p.stderr)
    return p.stdout.strip()
names=('alex.admin@corp.summit.test','taylor.admin@corp.summit.test','competitor-recovery')
users={name:pwd.getpwnam(name) for name in names}
gid=int(call(['getent','group','linux-workstation-admins@corp.summit.test']).split(':')[2])
root=pathlib.Path('/srv/summit-competition')
old=root/'Forensics.txt'
backup=pathlib.Path('/var/backups/summit-forensic-questions')
assert root.is_dir() and not root.is_symlink() and root.stat().st_uid==0
assert not backup.exists() and not backup.is_symlink(),'Question migration backup exists; refusing replacement'
assert old.is_file() and not old.is_symlink() and old.stat().st_uid==0,'Expected original shared sheet missing'
oldbytes=old.read_bytes()
templates={i:pathlib.Path('scenario-assets/Forensic-Question-%d.txt'%i).read_text() for i in (1,2,3)}
assert all(t.count('Answer =')==1 for t in templates.values()),'Unexpected question template'
legacy=[]
for name,user in users.items():
    desktop=pathlib.Path(user.pw_dir)/'Desktop'
    assert desktop.is_dir() and not desktop.is_symlink() and desktop.stat().st_uid==user.pw_uid
    shortcut=desktop/'Summit-Forensics.desktop'
    assert shortcut.is_file() and not shortcut.is_symlink() and shortcut.stat().st_uid==user.pw_uid
    assert 'Exec=gedit /srv/summit-competition/Forensics.txt\n' in shortcut.read_text(),'Legacy shortcut changed; refusing removal'
    legacy.append(shortcut)
    for number in (1,2,3):
        new=desktop/('Summit-Forensic-Question-%d.desktop'%number)
        assert not new.exists() and not new.is_symlink(),'Question shortcut already exists'
for destination in scenario.FORENSICS_FILES.values():
    path=pathlib.Path(destination)
    assert not path.exists() and not path.is_symlink(),'Question file already exists'
backup.mkdir(mode=0o700)
call(['cp','-a',str(old),str(backup/'Forensics.original.txt')])
for index,path in enumerate(legacy):
    call(['cp','-a',str(path),str(backup/('shortcut-%d.original'%index))])
created=[]
removed=[]
try:
    for issue in (17,18,19):
        number,correct=scenario.ANSWERS[issue]
        path=pathlib.Path(scenario.FORENSICS_FILES[issue])
        # Carry any existing submitted value into its own question document.
        import re
        values=re.findall(r'^Q%d[ \t]*=[ \t]*(.*?)[ \t]*$'%number,oldbytes.decode(),re.M)
        assert len(values)<=1,'Duplicate legacy answer; refusing ambiguous migration'
        submitted=values[0] if values else ''
        content=templates[number].replace('Answer =','Answer = '+submitted)
        with path.open('x') as f: f.write(content)
        created.append(path)
        os.chown(path,0,gid); path.chmod(0o664)
        call(['setfacl','-m','u:%d:rw-'%users['competitor-recovery'].pw_uid,str(path)])
        try:
            path.write_text(templates[number].replace('Answer =','Answer = '+correct))
            assert scenario.check(issue),'Correct answer failed to score for question %d'%number
            path.write_text(templates[number].replace('Answer =','Answer = incorrect'))
            assert not scenario.check(issue),'Incorrect answer scored for question %d'%number
        finally:
            path.write_text(content)
        for name,user in users.items():
            call(['runuser','-u',name,'--','test','-r',str(path)])
            call(['runuser','-u',name,'--','test','-w',str(path)])
            shortcut=pathlib.Path(user.pw_dir)/'Desktop'/('Summit-Forensic-Question-%d.desktop'%number)
            with shortcut.open('x') as f:
                f.write('[Desktop Entry]\nType=Application\nName=Forensic Question %d\nIcon=accessories-text-editor\nExec=gedit %s\nTerminal=false\n'%(number,path))
            created.append(shortcut)
            os.chown(shortcut,user.pw_uid,user.pw_gid); shortcut.chmod(0o755)
            call(['restorecon',str(shortcut)])
            subprocess.run(['runuser','-u',name,'--','gio','set',str(shortcut),'metadata::trusted','true'],capture_output=True,timeout=15)
    call(['restorecon','-R',str(root)])
    for path in legacy:
        path.unlink(); removed.append(path)
    assert old.read_bytes()==oldbytes,'Legacy answers changed during migration'
    old.unlink(); removed.append(old)
    # Remove the obsolete organizer desktop sheet too; keep its exact copy private.
    organizer=pathlib.Path('/home/jwang/Desktop/Forensics.txt')
    if organizer.is_file() and not organizer.is_symlink():
        call(['cp','-a',str(organizer),str(backup/'organizer-sheet.original.txt')])
        organizer.unlink()
    call(['install','-o','root','-g','root','-m','644','competition-ReadMe.conf',str(root/'Instructions.html')])
except BaseException:
    for index,path in enumerate(legacy):
        if path in removed: call(['cp','-a',str(backup/('shortcut-%d.original'%index)),str(path)])
    if old in removed: call(['cp','-a',str(backup/'Forensics.original.txt'),str(old)])
    # Leave new files available for diagnosis; do not discard submitted answers.
    print('Question migration aborted; original sheet/shortcuts restored and recovery records retained.',file=sys.stderr)
    raise
(backup/'migration.json').write_text(json.dumps({'users':names,'questions':scenario.FORENSICS_FILES,'positive_negative_tests':True,'previous_answers_preserved':True},indent=2)+'\n')
(backup/'migration.json').chmod(0o600)
print('Three separate forensic question files installed, each with its own Answer = section.')
print('Each approved competitor has three question icons. Old sheet/shortcut retired; private recovery copies retained.')
print('Correct/incorrect scoring and read/write access tested for every question and competitor.')
print('If GNOME has not trusted the new icons, use Allow Launching or gio metadata from that user session.')
PY
bash ./validate-probes.sh
