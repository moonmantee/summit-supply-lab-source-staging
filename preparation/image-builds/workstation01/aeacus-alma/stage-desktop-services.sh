#!/usr/bin/env bash
# Desktop, journal and explicitly unauthorized discovery/printing exercises.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import json,pathlib,subprocess,sys,time
sys.path.insert(0,'probes')
import access,core,policy
def call(args):
    return subprocess.run(args,text=True,capture_output=True,timeout=40,check=True)
backup=pathlib.Path('/var/backups/summit-desktop-service-stage')
config=pathlib.Path('/etc/dconf/db/local.d/90-summit-screenlock')
locks=pathlib.Path('/etc/dconf/db/local.d/locks/summit-screenlock')
journal=pathlib.Path('/etc/systemd/journald.conf.d/zz-summit-training.conf')
targets=(config,locks,journal)
assert not backup.exists(),'Batch already prepared; recovery record would be replaced'
for path in targets:
    assert not path.exists() and not path.is_symlink(),'Policy path already exists: '+str(path)
    for parent in path.parents:
        assert not parent.is_symlink(),'Symlink policy parent: '+str(parent)
profile=pathlib.Path('/etc/dconf/profile/user').read_text()
assert 'system-db:local' in profile.splitlines(),'Desktop profile does not use local system policy'
units=('avahi-daemon.service','avahi-daemon.socket','cups.service','cups.socket','cups.path')
original={}
for name in units:
    text=call(['systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','UnitFileState']).stdout
    state=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    assert state.get('LoadState')=='loaded' and state.get('UnitFileState')=='enabled' and state.get('ActiveState')=='active','Unexpected original service state: '+name
    original[name]=state
backup.mkdir(mode=0o700)
(backup/'original-services.json').write_text(json.dumps(original,indent=2)+'\n')
(backup/'original-services.json').chmod(0o600)
ids=(23,29,30,31)
created=set()
def write(path,text):
    path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    if path not in created:
        with path.open('x') as f:
            f.write(text)
        created.add(path)
    else:
        path.write_text(text)
    path.chmod(0o644)
def desktop(protected):
    write(config,'[org/gnome/desktop/screensaver]\nlock-enabled=%s\nlock-delay=uint32 0\n[org/gnome/desktop/session]\nidle-delay=uint32 %d\n'%('true' if protected else 'false',300 if protected else 0))
    write(locks,'/org/gnome/desktop/screensaver/lock-enabled\n/org/gnome/desktop/screensaver/lock-delay\n/org/gnome/desktop/session/idle-delay\n')
    call(['dconf','update'])
def journal_mode(persistent):
    write(journal,'[Journal]\nStorage=%s\n'%('persistent' if persistent else 'volatile'))
    if persistent:
        # tmpfiles applies distro journal permissions; no existing logs removed.
        call(['systemd-tmpfiles','--create','--prefix=/var/log/journal'])
        pathlib.Path('/var/log/journal').mkdir(mode=0o2755,exist_ok=True)
    call(['systemctl','restart','systemd-journald'])
    if persistent:
        call(['journalctl','--flush'])
def stop_services():
    call(['systemctl','disable','--now']+list(units))
    for _ in range(10):
        if core.evaluate(29,core.collect(29)) and core.evaluate(30,core.collect(30)):
            return
        time.sleep(0.5)
    raise AssertionError('Discovery/printing processes still running after deactivation')
def start_services():
    call(['systemctl','enable','--now']+list(units))
def clean():
    desktop(True); journal_mode(True); stop_services()
def plant():
    desktop(False); journal_mode(False); start_services()
def result():
    return {'23':policy.check(23),'29':core.evaluate(29,core.collect(29)),'30':core.evaluate(30,core.collect(30)),'31':access.check(31)}
def restore_original():
    for path in created:
        path.unlink()
    created.clear()
    call(['dconf','update']); call(['systemctl','restart','systemd-journald'])
    start_services()
records={}
try:
    clean(); records['clean']=result()
    assert all(records['clean'].values()),'Clean desktop/journal/service checks failed'
    plant(); records['planted']=result()
    assert not any(records['planted'].values()),'Planted state falsely awarded points'
    clean(); records['repaired']=result()
    assert all(records['repaired'].values()),'Desktop/journal/service repair failed'
    restore_original(); records['original_restored']=result()
    plant(); records['final_planted']=result()
    assert not any(records['final_planted'].values()),'Final planted state falsely awarded points'
except BaseException:
    restore_original()
    raise
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
print('Issues 23, 29, 30, 31: clean PASS, planted FAIL, repaired PASS, original policies restored, final planted FAIL.')
print('Existing journal data preserved. SSH, SSSD, firewall, and production scoring unchanged.')
print('Desktop logout/login and journal reboot retention still require final image verification.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
