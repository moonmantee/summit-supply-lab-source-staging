#!/usr/bin/env python3
"""One root entry point: forensic migration, full rehearsal, encrypted cutover."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from acceptance_helpers import require_state,scenario_fingerprint
import build_config
from forensic_helpers import SOLUTIONS,desktop_entry
from release_helpers import private_phocus,wait_scoring_report,cutover_transaction,require_report
from validate_results import collect

SOURCE=Path(__file__).resolve().parent
RUNTIME=Path('/opt/summit-shop01')
ENGINE=Path('/opt/aeacus')
QUESTIONS=Path('/srv/summit-shop01-forensics')
EVIDENCE=Path('/opt/summit-evidence/shop01')
MARKER='summit-shop-marker.service'
BACKUP=None
CREATED=[]
DIRECTORIES=[]
REHEARSAL=None
INTERRUPTION=None
ANSWER_WRITE_CODE=r'''
from pathlib import Path
import re,sys
p=Path(sys.argv[1])
t=p.read_text()
pattern=r'(?m)^Answer[ \t]*=[^\r\n]*(?:\r?\n|$)'
if len(re.findall(pattern,t))!=1:
    raise ValueError('Expected exactly one answer line')
p.write_text(re.sub(pattern,lambda m:'Answer = '+sys.argv[2]+'\n',t))
'''


def interrupted(signum,frame):
    global INTERRUPTION
    if REHEARSAL is not None and REHEARSAL.poll() is None:
        if INTERRUPTION is None:
            INTERRUPTION=signum
            try: REHEARSAL.send_signal(signum)
            except ProcessLookupError: pass
        # Do not interrupt the child a second time while it restores its snapshot.
        return
    raise RuntimeError('Interrupted '+str(signum))


def run_rehearsal(command,timeout=1800):
    global REHEARSAL,INTERRUPTION
    INTERRUPTION=None
    # Isolate from terminal Ctrl-C so only the parent forwards one signal.
    REHEARSAL=subprocess.Popen(command,start_new_session=True)
    try:
        try: result=REHEARSAL.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            interrupted(signal.SIGTERM,None)
            try: result=REHEARSAL.wait(timeout=900)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Rehearsal restoration is still running; do not start migration rollback')
        if result or INTERRUPTION is not None: raise RuntimeError('Combined rehearsal stopped after child recovery')
    finally:
        if REHEARSAL.poll() is not None: REHEARSAL=None


def call(args,cwd=None,timeout=240):
    p=subprocess.run([str(x) for x in args],cwd=cwd,text=True,capture_output=True,timeout=timeout)
    with (BACKUP/'commands.log').open('a') as log: log.write(repr(args)+'\n'+p.stdout+p.stderr+'\n')
    if p.returncode: raise RuntimeError('Command failed: '+str(args[0])+'; private commands.log')
    return p.stdout


def safe(path):
    path=Path(path)
    if any(p.is_symlink() for p in [path,*path.parents]): raise RuntimeError('Symlink refused: '+str(path))
    return path


def mkdir(path,mode=0o755,owner=None):
    path=safe(path)
    if not path.exists():
        if not path.parent.is_dir(): mkdir(path.parent)
        path.mkdir(mode=mode); path.chmod(mode); DIRECTORIES.append(path)
        if owner: os.chown(path,owner.pw_uid,owner.pw_gid)
    elif not path.is_dir(): raise RuntimeError('Expected directory: '+str(path))


def new_file(path,text,mode=0o644,owner=None):
    path=safe(path)
    with path.open('x',encoding='utf-8',newline='\n') as stream: stream.write(text)
    CREATED.append(path); path.chmod(mode)
    if owner: os.chown(path,owner.pw_uid,owner.pw_gid)


def preflight():
    import pwd
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='shop01': raise RuntimeError('Run with sudo on shop01')
    if SOURCE.stat().st_uid!=0 or SOURCE.stat().st_mode & 0o077: raise RuntimeError('Use private entry point')
    if 'VERSION_ID="24.04"' not in Path('/etc/os-release').read_text(): raise RuntimeError('Expected reviewed Ubuntu version')
    for path in (RUNTIME,ENGINE):
        safe(path)
        if path.stat().st_uid!=0: raise RuntimeError('Unexpected runtime ownership')
    old=json.loads((RUNTIME/'competition-manifest.json').read_text())
    if any(x['category']!='Persistence' for x in old['issues'][37:]): raise RuntimeError('Already migrated or unexpected scenario')
    for path in (QUESTIONS,EVIDENCE):
        safe(path)
        if path.exists(): raise RuntimeError('Forensic destination already exists; retain recovery records')
    for binary in ('/usr/bin/gnome-text-editor','/usr/bin/setfacl','/usr/bin/unshare','/usr/bin/mount'):
        if not Path(binary).is_file(): raise RuntimeError('Missing prerequisite: '+binary)
    users=[pwd.getpwnam(name) for name in ('jwang','summit_editor','summit_employee','summit_support')]
    # Discover only existing domain homes whose NSS identity resolves to that exact home.
    for home in Path('/home').iterdir():
        if home.name.endswith('@corp.summit.test'):
            user=pwd.getpwnam(home.name)
            if user.pw_dir!=str(home): raise RuntimeError('Domain home identity mismatch')
            users.append(user)
    for user in users:
        home=safe(user.pw_dir)
        if not home.is_dir() or home.stat().st_uid!=user.pw_uid: raise RuntimeError('Participant home ownership mismatch')
    return users


def snapshot_production():
    archive=BACKUP/'production.tar'
    if archive.exists(): raise RuntimeError('Original production rollback is immutable')
    pending=BACKUP/'production.pending.tar'
    call(['tar','--acls','--xattrs','--numeric-owner','-cpf',pending,'-C','/','opt/aeacus','opt/summit-shop01'])
    call(['tar','-tf',pending])
    pending.rename(archive)


def rollback():
    call(['systemctl','stop','summit-aeacus'])
    # Candidate files were copied into existing runtime; restore only newly added leaves.
    old=set(json.loads((BACKUP/'runtime-files.json').read_text()))
    for path in sorted(RUNTIME.rglob('*'),key=lambda p:len(p.parts),reverse=True):
        if str(path.relative_to(RUNTIME)) not in old:
            if path.is_dir() and not path.is_symlink(): path.rmdir()
            else: path.unlink()
    for name in ('scoring.conf','scoring.dat','ReadMe.conf'):
        safe(ENGINE/name).unlink(missing_ok=True)
    call(['tar','--acls','--xattrs','--numeric-owner','-xpf',BACKUP/'production.tar','-C','/'])
    call(['tar','--acls','--xattrs','--numeric-owner','-xpf',BACKUP/'markers.tar','-C','/'])
    call(['systemctl','daemon-reload']); call(['systemctl','enable','--now',MARKER])
    for path in reversed(CREATED): safe(path).unlink(missing_ok=True)
    for path in reversed(DIRECTORIES):
        if path.exists(): safe(path).rmdir()
    call(['systemctl','start','summit-aeacus'])
    require_state(collect(RUNTIME),False)
    call(['python3','-c','import importlib.util; s=importlib.util.spec_from_file_location("rehearsal","rehearse-all.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.check_business()'],cwd=SOURCE)
    (BACKUP/'rollback-verified.json').write_text('{"verified":true,"points":0}\n')
    print('Original forty remediation checks restored at 0/100. Private recovery: '+str(BACKUP),flush=True)


def install_questions(users):
    mkdir(QUESTIONS); mkdir(EVIDENCE)
    # Directory ACL/default ACL permits editor atomic saves and retains shared access.
    acls=','.join('u:%d:rwx'%u.pw_uid for u in users)
    call(['setfacl','-m',acls,QUESTIONS])
    call(['setfacl','-d','-m','u::rwx,g::r-x,o::r-x,'+acls,QUESTIONS])
    for name in ('apache-access.log','journal-excerpt.log','incident-summary.txt'):
        new_file(EVIDENCE/name,(SOURCE/'forensic-assets'/name).read_text(),0o444)
    for number in (1,2,3):
        path=QUESTIONS/('Forensic-Question-%d.txt'%number)
        new_file(path,(SOURCE/'forensic-assets'/path.name).read_text())
        call(['setfacl','-m',','.join('u:%d:rw-'%u.pw_uid for u in users),path])
    for user in users:
        for name in ('apache-access.log','journal-excerpt.log','incident-summary.txt'):
            call(['runuser','-u',user.pw_name,'--','test','-r',EVIDENCE/name])
            p=subprocess.run(['runuser','-u',user.pw_name,'--','test','-w',str(EVIDENCE/name)])
            if p.returncode!=1: raise RuntimeError('Evidence must be read-only for participants')
        desktop=Path(user.pw_dir)/'Desktop'
        config=Path(user.pw_dir)/'.config/user-dirs.dirs'
        if config.is_file():
            import re
            matches=re.findall(r'^XDG_DESKTOP_DIR="([^"\n]+)"$',config.read_text(),re.M)
            if len(matches)>1: raise RuntimeError('Ambiguous desktop folder')
            if matches: desktop=Path(matches[0].replace('$HOME',user.pw_dir))
        desktop=safe(desktop)
        if not desktop.is_relative_to(Path(user.pw_dir)) or desktop==Path(user.pw_dir): raise RuntimeError('Unexpected desktop location')
        mkdir(desktop,owner=user)
        if desktop.stat().st_uid!=user.pw_uid: raise RuntimeError('Desktop owner mismatch')
        for number in (1,2,3):
            icon=desktop/('Summit-Forensic-Question-%d.desktop'%number)
            new_file(icon,desktop_entry(number),0o755,user)
            call(['desktop-file-validate',icon])
            call(['runuser','-u',user.pw_name,'--','test','-r',icon])
            call(['runuser','-u',user.pw_name,'--','test','-x',icon])
            # Trust metadata needs a logged-in GNOME user bus; record separately if unavailable.
            env=['env','HOME='+user.pw_dir,'XDG_RUNTIME_DIR=/run/user/'+str(user.pw_uid),
                 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(user.pw_uid)+'/bus']
            p=subprocess.run(['runuser','-u',user.pw_name,'--']+env+['gio','set',str(icon),'metadata::trusted','true'],capture_output=True,text=True,timeout=20)
            if p.returncode:
                with (BACKUP/'desktop-trust-pending.txt').open('a') as pending:
                    pending.write(user.pw_name+': '+str(icon)+'\n')
        for issue,answer in SOLUTIONS.items():
            path=QUESTIONS/('Forensic-Question-%d.txt'%(issue-37)); original=path.read_text()
            try:
                for value,expected in ((answer,'PASS'),('incorrect','FAIL'),('','FAIL')):
                    call(['runuser','-u',user.pw_name,'--','python3','-c',ANSWER_WRITE_CODE,path,value])
                    token=call(['python3',SOURCE/'probes/check.py',str(issue)]).strip()
                    if token!=expected:
                        raise RuntimeError('Forensic behavior mismatch: objective %d, identity %s, expected %s, got %s'%(issue,user.pw_name,expected,token))
            finally: path.write_text(original)
    print('Three questions: correct/incorrect/blank scoring and reading/saving verified for '+str(len(users))+' participant identities.',flush=True)


def retire_markers():
    Path('/etc/cron.d/summit-shop-marker').unlink()
    call(['systemctl','disable','--now',MARKER])
    Path('/etc/systemd/system/'+MARKER).unlink()
    call(['systemctl','daemon-reload'])
    Path('/opt/summit-shop-training/suid-marker').chmod(0o755)
    sys.path.insert(0,str(SOURCE/'probes'))
    import persistence
    if not all(persistence.check(i) for i in (38,39,40)): raise RuntimeError('Old persistence fixtures remain enabled')


def candidate():
    runtime=BACKUP/'candidate-runtime'; shutil.copytree(RUNTIME,runtime)
    for p in (SOURCE/'probes').glob('*.py'):
        if not p.name.startswith('test_'): shutil.copyfile(p,runtime/'probes'/p.name); (runtime/'probes'/p.name).chmod(0o600)
    for name in ('competition-manifest.json','release_helpers.py','validate_results.py','verify-release.py','acceptance_helpers.py'):
        shutil.copyfile(SOURCE/name,runtime/name); (runtime/name).chmod(0o600)
    directory=BACKUP/'candidate'; directory.mkdir(mode=0o700)
    shutil.copytree(ENGINE/'assets',directory/'assets')
    (directory/'assets/previous.txt').write_text('0')
    shutil.copyfile(ENGINE/'TeamID.txt',directory/'TeamID.txt')
    (directory/'ReadMe.conf').write_text((SOURCE/'ReadMe.conf').read_text())
    (directory/'scoring.conf').write_text(build_config.render(json.loads((SOURCE/'competition-manifest.json').read_text())))
    # Native check/encrypt/readme need plaintext; Phocus alone proves encrypted evaluation.
    for action in ('check','readme','encrypt'): call([ENGINE/'aeacus','--dir',str(directory)+'/',action],cwd=directory)
    (directory/'scoring.dat').chmod(0o600); (directory/'scoring.conf').unlink()
    private_phocus(directory,ENGINE/'phocus',runtime=runtime)
    print('Encrypted candidate verified at final probe paths: 0/100, forty checks.',flush=True)
    return directory,runtime


def apply(prepared):
    directory,runtime=prepared
    call(['cp','-a',str(runtime)+'/.',RUNTIME])
    for name in ('scoring.dat','ReadMe.conf'):
        shutil.copyfile(directory/name,ENGINE/name); (ENGINE/name).chmod(0o600)
    shutil.copyfile(directory/'assets/ReadMe.html',ENGINE/'assets/ReadMe.html')
    (ENGINE/'assets/ReadMe.html').chmod(0o644)
    report=ENGINE/'assets/ScoringReport.html'; report.unlink(missing_ok=True)
    call(['systemctl','start','summit-aeacus'])
    wait_scoring_report(report,lambda: subprocess.run(['systemctl','is-active','--quiet','summit-aeacus']).returncode==0,timeout=180)
    report.chmod(0o644); require_state(collect(RUNTIME),False)
    call(['python3',RUNTIME/'verify-release.py'],timeout=180)


def main():
    global BACKUP
    os.umask(0o077)
    users=preflight()
    BACKUP=Path(tempfile.mkdtemp(prefix='summit-shop01-forensics-',dir='/var/backups'))
    print('Private forensic migration recovery: '+str(BACKUP),flush=True)
    require_state(collect(RUNTIME),False)
    call(['systemctl','is-active','--quiet','summit-aeacus'])
    # Exact known marker identity is required before disabling/removing its activation.
    marker=Path('/etc/systemd/system')/MARKER
    if marker.read_bytes()!=Path('/var/backups/summit-shop01-persistence-qwZSdyD9/marker.service').read_bytes(): raise RuntimeError('Marker unit changed')
    if Path('/etc/cron.d/summit-shop-marker').read_text()!='*/5 * * * * summit_shop_marker /opt/summit-shop-training/cron-marker.sh\n': raise RuntimeError('Marker cron changed')
    call(['systemctl','is-active','--quiet',MARKER])
    if call(['systemctl','is-enabled',MARKER]).strip()!='enabled': raise RuntimeError('Marker enablement changed')
    (BACKUP/'runtime-files.json').write_text(json.dumps([str(p.relative_to(RUNTIME)) for p in RUNTIME.rglob('*')]))
    signal.signal(signal.SIGINT,interrupted); signal.signal(signal.SIGTERM,interrupted)
    # Take a consistent immutable snapshot while the scorer is briefly stopped.
    call(['systemctl','stop','summit-aeacus'])
    try: snapshot_production()
    finally: call(['systemctl','start','summit-aeacus'])
    call(['tar','--acls','--xattrs','--numeric-owner','-cpf',BACKUP/'markers.tar','-C','/',
          'etc/cron.d/summit-shop-marker','etc/systemd/system/summit-shop-marker.service',
          'etc/systemd/system/multi-user.target.wants/summit-shop-marker.service','opt/summit-shop-training/suid-marker'])
    try:
        install_questions(users)
        # Rehearsal emits only status/progress; keep its meaningful phases visible.
        run_rehearsal(['python3',str(SOURCE/'rehearse-all.py')])
        proof=json.loads(Path('/home/jwang/shop01-combined-rehearsal.json').read_text())
        bank=Path(proof['backup'])
        if json.loads((bank/'source-hashes.json').read_text())!=scenario_fingerprint(SOURCE): raise RuntimeError('Combined proof differs')
        retire_markers(); require_state(collect(SOURCE),False)
        prepared=candidate()
        # Everything above is prepared and proven while the old runtime remains active.
        cutover_transaction(prepare=lambda:prepared,stop=lambda:call(['systemctl','stop','summit-aeacus']),
                            snapshot=lambda:None,apply=apply,rollback=lambda:None,
                            resume=lambda:None,cleanup=lambda:None)
    except BaseException as error:
        (BACKUP/'failure.txt').write_text(str(error)+'\n')
        if REHEARSAL is not None and REHEARSAL.poll() is None:
            print('Rehearsal recovery remains active; leave its process running. Private records: '+str(BACKUP),flush=True)
            raise
        print('Migration stopped; restoring original scorer and marker state.',flush=True)
        try: rollback()
        except BaseException as recovery:
            (BACKUP/'rollback-failure.txt').write_text(str(recovery)+'\n')
            print('RESTORATION NEEDS CONSOLE ATTENTION: '+str(BACKUP),flush=True)
        raise
    (BACKUP/'completed.json').write_text(json.dumps({'count':40,'total_points':100,'forensic_questions':3,'points':0,'users':[u.pw_name for u in users]})+'\n')
    upload=Path('/home/jwang/shop01-forensic-update')
    if upload.is_dir() and not upload.is_symlink():
        shutil.move(str(upload),str(BACKUP/'organizer-upload'))
        call(['chown','-R','root:root',BACKUP/'organizer-upload'])
        for p in (BACKUP/'organizer-upload').rglob('*'):
            if not p.is_symlink(): p.chmod(0o700 if p.is_dir() else 0o600)
    print('Three forensic questions and desktop icons deployed; encrypted 40-check/100-point scorer active at 0/100.',flush=True)
    if (BACKUP/'desktop-trust-pending.txt').exists():
        print('GNOME icon trust remains to verify in participant sessions; use Allow Launching if prompted.',flush=True)
    print('Private recovery: '+str(BACKUP)+'; reboot/domain/manual desktop acceptance remains.',flush=True)


if __name__=='__main__': main()
