#!/usr/bin/env bash
# Download-only preparation. No installed packages, services, or auth policies changed.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 -m unittest discover -s . -p test_recovery_state.py
python3 - <<'PY'
import hashlib,json,pathlib,subprocess,datetime
from recovery_state import ensure_directory,preserve_file
def call(args):
    return subprocess.run(args,text=True,capture_output=True,timeout=900,check=True)
root=pathlib.Path('/var/backups/summit-package-recovery-retry1')
assert not (root/'inventory.json').exists(),'Completed inventory exists; use the software stage instead of repeating preparation'
original=call(['rpm','-qa','--qf','%{NEVRA}\n']).stdout
installed=sorted(original.splitlines())
cockpit=[]
for name in ('cockpit','cockpit-ws'):
    version=call(['rpm','-q','--qf','%{NEVRA}',name]).stdout
    assert version and version in installed,'Missing Cockpit package: '+name
    cockpit.append(version)
ensure_directory(root,owner=0)
recovery=root/'cockpit-original'; candidates=root/'candidates'
ensure_directory(recovery,owner=0); ensure_directory(candidates,owner=0)
download_original=root/'download-original'; download_candidates=root/'download-candidates'
ensure_directory(download_original,owner=0); ensure_directory(download_candidates,owner=0)
# Package query ordering is not significant; compare the sorted original set.
before=root/'installed-before.txt'
if before.exists():
    assert before.is_file() and not before.is_symlink() and before.stat().st_uid==0,'Unsafe original package record'
    assert sorted(before.read_text().splitlines())==installed,'Installed package set differs from saved baseline; refusing resume'
else:
    preserve_file(before,original.encode(),owner=0)
base=['dnf','-y','--disablerepo=*','--enablerepo=baseos','--enablerepo=appstream','--enablerepo=extras','--setopt=gpgcheck=1','--setopt=keepcache=1']
commands=[base+['reinstall','--downloadonly','--downloaddir='+str(download_original)]+cockpit,
          base+['install','--downloadonly','--downloaddir='+str(download_candidates),'nmap','dnf-automatic']]
logs=[]
attempt=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
try:
    for index,args in enumerate(commands,1):
        print('Downloading package set %d of 2; installed software is unchanged.'%index,flush=True)
        p=subprocess.run(args,text=True,capture_output=True,timeout=900)
        log=root/('download-%s-%d.log'%(attempt,index))
        preserve_file(log,(p.stdout+p.stderr).encode(),owner=0)
        logs.append(str(log))
        if p.returncode:
            print((p.stdout+p.stderr)[-2500:])
            raise RuntimeError('Download failed; original installed packages retained. Log: '+str(log))
    after=sorted(call(['rpm','-qa','--qf','%{NEVRA}\n']).stdout.splitlines())
    assert installed==after,'Installed package set changed during download-only preparation'
    # DNF tracks downloaded paths and may remove them during a later successful
    # transaction. Recovery masters are separate copies, never download targets.
    for source,destination in ((download_original,recovery),(download_candidates,candidates)):
        for path in source.glob('*.rpm'):
            assert path.is_file() and not path.is_symlink(),'Unsafe downloaded RPM: '+str(path)
            preserve_file(destination/path.name,path.read_bytes(),owner=0)
    inventory=[]
    for directory in (recovery,candidates):
        for path in sorted(directory.glob('*.rpm')):
            signature=call(['rpm','--checksig',str(path)]).stdout.strip()
            assert 'signatures OK' in signature,'RPM signature not confirmed: '+str(path)
            nevra=call(['rpm','-qp','--qf','%{NEVRA}',str(path)]).stdout
            inventory.append({'file':str(path),'nevra':nevra,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'signature':signature})
    assert set(cockpit)<={r['nevra'] for r in inventory if r['file'].startswith(str(recovery)+'/')},'Exact Cockpit recovery RPMs are missing'
    for name in ('nmap','dnf-automatic'):
        assert any(call(['rpm','-qp','--qf','%{NAME}',r['file']]).stdout==name for r in inventory if r['file'].startswith(str(candidates)+'/')),'Candidate missing: '+name
    report={'approved_repositories':['baseos','appstream','extras'],'installed_package_set_unchanged':True,'rpms':inventory,'logs':logs}
    preserve_file(root/'inventory.json',(json.dumps(report,indent=2)+'\n').encode(),owner=0)
    print('Verified %d signed RPMs; exact Cockpit recovery packages retained.'%len(inventory))
    print('Download-only preparation complete. No packages installed or removed; no services changed.')
except BaseException:
    after=sorted(call(['rpm','-qa','--qf','%{NEVRA}\n']).stdout.splitlines())
    print('Installed package set unchanged: '+str(installed==after))
    raise
PY
