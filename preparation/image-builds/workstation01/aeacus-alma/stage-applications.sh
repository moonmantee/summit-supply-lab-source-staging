#!/usr/bin/env bash
# Reversible application batch: issues 9,10,12,13,14,33.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 -m unittest discover -s . -p test_application_stage.py
python3 - <<'PY'
import datetime,json,os,pathlib,stat,subprocess,sys
sys.path.insert(0,'probes')
import policy
from application_stage import firefox_state,dnf_state
ids=(9,10,12,13,14,33)
permissions=[pathlib.Path('/etc/summit-workstation/app.conf'),pathlib.Path('/etc/profile.d/summit-workstation.sh')]
dnf=pathlib.Path('/etc/dnf/dnf.conf')
browser=pathlib.Path('/etc/firefox/policies/policies.json')
backup=pathlib.Path('/var/backups/summit-application-stage')
assert not backup.exists(),'Batch already prepared; refusing to overwrite recovery backup'
for path in permissions+[dnf,browser]:
    assert not path.is_symlink(),'Symlink target: '+str(path)
    if path.exists():
        s=path.stat()
        assert stat.S_ISREG(s.st_mode) and s.st_uid==0,'Unexpected target ownership/type: '+str(path)
    for parent in path.parents:
        assert not parent.is_symlink(),'Symlink parent: '+str(parent)
        if parent.exists():
            s=parent.stat()
            assert s.st_uid==0 and not s.st_mode & 0o022,'Writable parent: '+str(parent)
assert all(policy.check(i) for i in (12,13,14,33)),'Existing file/update protections fail; no staging performed'
original_dnf=dnf.read_text()
original_browser=json.loads(browser.read_text()) if browser.exists() else {}
# Validate both transformations before saving or changing anything.
clean_browser=firefox_state(original_browser,True)
planted_browser=firefox_state(original_browser,False)
planted_dnf=dnf_state(original_dnf,True)
original_modes={str(p):stat.S_IMODE(p.stat().st_mode) for p in permissions}
backup.mkdir(mode=0o700)
browser_existed=browser.exists()
subprocess.run(['cp','-a',str(dnf),str(backup/'dnf.conf')],check=True)
if browser_existed:
    subprocess.run(['cp','-a',str(browser),str(backup/'policies.json')],check=True)
metadata={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'browser_existed':browser_existed,'original_modes':original_modes,'issues':ids}
(backup/'original-state.json').write_text(json.dumps(metadata,indent=2)+'\n')
(backup/'original-state.json').chmod(0o600)
browser.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
def browser_write(data):
    browser.write_text(json.dumps(data,indent=2)+'\n')
    browser.chmod(0o644)
def clean():
    browser_write(clean_browser)
    dnf.write_text(original_dnf)
    for p in permissions:
        p.chmod(original_modes[str(p)])
def plant():
    browser_write(planted_browser)
    dnf.write_text(planted_dnf)
    for p in permissions:
        p.chmod(0o666)
def result():
    return {str(i):policy.check(i) for i in ids}
def restore_original():
    subprocess.run(['cp','-a',str(backup/'dnf.conf'),str(dnf)],check=True)
    if browser_existed:
        subprocess.run(['cp','-a',str(backup/'policies.json'),str(browser)],check=True)
    elif browser.exists():
        browser.unlink()
    for p in permissions:
        p.chmod(original_modes[str(p)])
records={}
try:
    clean(); records['clean']=result()
    assert all(records['clean'].values()),'Clean checks failed'
    plant(); records['planted']=result()
    assert not any(records['planted'].values()),'Planted state falsely earned credit'
    clean(); records['repaired']=result()
    assert all(records['repaired'].values()),'Repair failed'
    # Rehearse exact original configuration recovery as well as the clean fix.
    restore_original(); records['original_restored']=result()
    assert dnf.read_text()==original_dnf,'Original DNF state was not restored'
    assert (json.loads(browser.read_text()) if browser.exists() else {})==original_browser,'Original browser state was not restored'
    plant(); records['final_planted']=result()
    assert not any(records['final_planted'].values()),'Final planted checks falsely earned credit'
except BaseException:
    restore_original()
    raise
subprocess.run(['restorecon',str(dnf),str(browser)],check=True)
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
print('Issues 9, 10, 12, 13, 14, 33: clean PASS, planted FAIL, repaired PASS, original restored, final planted FAIL.')
print('Six application weaknesses planted. Recovery backup: '+str(backup))
print('Restart Firefox before inspecting the browser policy in the desktop; no process was forcibly closed.')
PY
# Isolated engine verification; production remains the original baseline.
bash /home/jwang/aeacus-setup/validate-probes.sh
