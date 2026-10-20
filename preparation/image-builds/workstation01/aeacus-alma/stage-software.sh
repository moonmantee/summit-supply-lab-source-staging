#!/usr/bin/env bash
# Local signed RPM rehearsal for prohibited Nmap and Cockpit software.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
if [[ ! -f /var/backups/summit-package-recovery-retry1/inventory.json ]]; then
  bash /home/jwang/aeacus-setup/prepare-package-recovery.sh
fi
python3 -m unittest discover -s . -p test_package_tools.py
python3 - <<'PY'
import hashlib,json,os,pathlib,subprocess,sys
sys.path.insert(0,'probes')
import policy,scenario
from package_tools import run_package_command
def call(args):
    return run_package_command(args)
recovery=pathlib.Path('/var/backups/summit-package-recovery-retry1')
backup=pathlib.Path('/var/backups/summit-software-stage-retry1')
assert not backup.exists(),'Software batch already prepared; refusing to replace backup'
inventory=json.loads((recovery/'inventory.json').read_text())
assert inventory['installed_package_set_unchanged'] is True,'Unverified recovery package set'
original={name:call(['rpm','-q','--qf','%{NEVRA}',name]).stdout for name in ('cockpit','cockpit-ws')}
rpms={}
for entry in inventory['rpms']:
    path=pathlib.Path(entry['file'])
    assert not path.is_symlink() and path.is_file() and str(path).startswith(str(recovery)+'/'),'Unsafe recovery path'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256'],'RPM hash mismatch: '+str(path)
    assert 'signatures OK' in call(['rpm','--checksig',str(path)]).stdout,'Unsigned/untrusted RPM'
    name=call(['rpm','-qp','--qf','%{NAME}',str(path)]).stdout
    rpms[name]=path
assert {'cockpit','cockpit-ws','nmap'}<=rpms.keys(),'Missing software rehearsal RPMs'
for name in ('cockpit','cockpit-ws'):
    assert call(['rpm','-qp','--qf','%{NEVRA}',str(rpms[name])]).stdout==original[name],'Recovery version differs: '+name
assert scenario.check(36),'Nmap already present or absence check unavailable'
call(['rpm','-e','--test','cockpit','cockpit-ws'])
original_units={}
for name in ('cockpit.socket','cockpit.service'):
    text=call(['systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','UnitFileState']).stdout
    original_units[name]=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
assert original_units['cockpit.socket'].get('LoadState')=='loaded','Cockpit socket missing'
assert original_units['cockpit.socket'].get('UnitFileState') in ('enabled','disabled'),'Unexpected original Cockpit socket state'
backup.mkdir(mode=0o700)
(backup/'original-state.json').write_text(json.dumps({'packages':original,'units':original_units},indent=2)+'\n')
(backup/'original-state.json').chmod(0o600)
base=['dnf','-y','--disablerepo=*','--setopt=gpgcheck=1','--setopt=localpkg_gpgcheck=1','--setopt=keepcache=1']
def installed(name):
    p=subprocess.run(['rpm','-q',name],text=True,capture_output=True,timeout=30,env=dict(os.environ,LC_ALL='C'))
    if p.returncode==0:
        return True
    assert p.returncode==1 and p.stdout.strip()=='package %s is not installed'%name,'RPM lookup failed: '+name
    return False
def cockpit_remove():
    call(['systemctl','disable','--now','cockpit.socket'])
    call(['systemctl','stop','cockpit.service'])
    call(['rpm','-e','cockpit','cockpit-ws'])
    call(['systemctl','daemon-reload'])
def cockpit_install():
    call(base+['install',str(rpms['cockpit']),str(rpms['cockpit-ws'])])
    call(['systemctl','daemon-reload'])
    # Presence is sufficient for the unauthorized-software exercise; web
    # administration is left disabled instead of opening a new listener.
    call(['systemctl','disable','--now','cockpit.socket'])
def nmap_install():
    call(base+['install',str(rpms['nmap'])])
def nmap_remove():
    call(['rpm','-e','--test','nmap'])
    call(['rpm','-e','nmap'])
def result():
    return {'35':policy.check(35),'36':scenario.check(36)}
def verify_masters():
    for entry in inventory['rpms']:
        path=pathlib.Path(entry['file'])
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256'],'Recovery RPM disappeared/changed: '+str(path)
def restore_original():
    if installed('nmap'):
        nmap_remove()
    if not installed('cockpit') or not installed('cockpit-ws'):
        cockpit_install()
    socket=original_units['cockpit.socket']
    call(['systemctl','enable' if socket['UnitFileState']=='enabled' else 'disable','cockpit.socket'])
    for name,state in original_units.items():
        call(['systemctl','start' if state['ActiveState']=='active' else 'stop',name])
records={}
try:
    cockpit_remove(); records['clean']=result()
    assert all(records['clean'].values()),'Clean software-removal checks failed'
    cockpit_install(); verify_masters(); nmap_install(); verify_masters(); records['planted']=result()
    assert not any(records['planted'].values()),'Installed prohibited software falsely earned points'
    cockpit_remove(); nmap_remove(); records['repaired']=result()
    assert all(records['repaired'].values()),'Software remediation failed'
    restore_original()
    assert all(call(['rpm','-q','--qf','%{NEVRA}',name]).stdout==version for name,version in original.items()),'Original versions not restored'
    records['original_restored']=result()
    call(['systemctl','disable','--now','cockpit.socket'])
    call(['systemctl','stop','cockpit.service'])
    nmap_install(); verify_masters(); records['final_planted']=result()
    assert not any(records['final_planted'].values()),'Final software state falsely earned points'
except BaseException:
    restore_original()
    raise
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
print('Issues 35, 36: clean PASS, planted FAIL, repaired PASS, original versions restored, final planted FAIL.')
print('Signed local RPMs only. Cockpit socket remains disabled; no new web listener enabled.')
print('SSH, SSSD, authentication policies and production scorer unchanged.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
