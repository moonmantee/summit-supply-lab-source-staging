#!/usr/bin/env bash
# Harmless marker-only cron/systemd practice. No network callbacks, no root payloads.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import hashlib,json,pathlib,subprocess,sys,time
sys.path.insert(0,'probes')
import scenario
def call(args):
    return subprocess.run(args,text=True,capture_output=True,timeout=30,check=True)
runner='summit-marker-runner'
account=subprocess.run(['getent','passwd',runner],capture_output=True)
assert account.returncode==2,'Runner account already exists or lookup failed'
payload_dir=pathlib.Path('/usr/local/lib/summit-training')
assert payload_dir.is_dir() and not payload_dir.is_symlink(),'Missing/unsafe payload directory'
targets={
 'cron-marker.sh':payload_dir/'cron-marker.sh',
 'systemd-marker.sh':payload_dir/'systemd-marker.sh',
 'summit-marker.cron':pathlib.Path('/etc/cron.d/summit-marker'),
 'summit-marker.service':pathlib.Path('/etc/systemd/system/summit-marker.service'),
 'summit-marker.timer':pathlib.Path('/etc/systemd/system/summit-marker.timer'),
}
for path in targets.values():
    assert not path.exists() and not path.is_symlink(),'Target exists: '+str(path)
for name in ('summit-marker.timer','summit-marker.service'):
    p=subprocess.run(['systemctl','show',name,'-p','LoadState','-p','ActiveState'],text=True,capture_output=True,timeout=30)
    # systemctl may return 1 for an absent unit; require explicit structured
    # absence, rather than treating every command error as missing.
    assert p.returncode in (0,1) and 'LoadState=not-found' in p.stdout and 'ActiveState=inactive' in p.stdout,'Existing persistence unit or lookup failure'
assert scenario.check(24) and scenario.check(25),'Clean persistence checks failed; nothing changed'
source=pathlib.Path('scenario-assets')
inventory=json.loads(pathlib.Path('artifact-hashes.json').read_text())
for name in targets:
    assert hashlib.sha256((source/name).read_bytes()).hexdigest()==inventory[name],'Asset mismatch: '+name
assert pathlib.Path('/opt/summit-evidence/systemd-marker.sh').read_bytes()==scenario.PAYLOAD,'Preserved forensic evidence differs'
assert call(['systemctl','is-active','crond']).stdout.strip()=='active','Cron daemon is unavailable'
backup=pathlib.Path('/var/backups/summit-persistence-stage')
assert not backup.exists(),'Batch already staged; refusing to replace rehearsal'
backup.mkdir(mode=0o700)
records={'clean':{'24':True,'25':True}}
runner_created=False
created={}
unit_mutations=False
def install():
    global unit_mutations
    for name,path in targets.items():
        data=(source/name).read_bytes()
        if name=='summit-marker.cron':
            data=data.replace(b' root ',b' '+runner.encode()+b' ')
        elif name=='summit-marker.service':
            # Private temporary namespace and read-only system; preserved inert
            # payload executes as a dedicated unprivileged system identity.
            data+=('User='+runner+'\nGroup='+runner+'\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\n').encode()
        with path.open('xb') as f:
            f.write(data)
        created[path]=hashlib.sha256(data).hexdigest()
        path.chmod(0o755 if name.endswith('.sh') else 0o644)
    call(['restorecon','-R',str(payload_dir),str(targets['summit-marker.cron'])])
    call(['systemctl','daemon-reload'])
    unit_mutations=True
    call(['systemctl','enable','--now','summit-marker.timer'])
    call(['systemctl','start','summit-marker.service'])
    status=call(['systemctl','show','summit-marker.service','-p','Result','-p','ExecMainStatus']).stdout
    assert 'Result=success' in status and 'ExecMainStatus=0' in status,'Systemd payload did not run successfully'
    call(['runuser','-u',runner,'--','/bin/sh',str(targets['cron-marker.sh'])])
def remove_owned():
    global unit_mutations
    if unit_mutations:
        # Only our previously absent unit names are stopped/disabled.
        call(['systemctl','disable','--now','summit-marker.timer'])
        call(['systemctl','stop','summit-marker.service'])
        unit_mutations=False
    for path,digest in list(created.items()):
        assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Changed artifact; cleanup refused: '+str(path)
        path.unlink()
        del created[path]
    call(['systemctl','daemon-reload'])
def result():
    return {str(i):scenario.check(i) for i in (24,25)}
try:
    call(['useradd','--system','--user-group','--no-create-home','--home-dir','/nonexistent','--shell','/sbin/nologin',runner])
    runner_created=True
    call(['passwd','--lock',runner])
    install(); records['planted']=result()
    assert not any(records['planted'].values()),'Planted checks falsely awarded points'
    remove_owned(); records['repaired']=result()
    assert all(records['repaired'].values()),'Repair checks failed'
    install(); records['final_planted']=result()
    assert not any(records['final_planted'].values()),'Final planted checks falsely awarded points'
except BaseException:
    remove_owned()
    if runner_created:
        call(['userdel',runner])
    raise
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
assert pathlib.Path('/opt/summit-evidence/systemd-marker.sh').read_bytes()==scenario.PAYLOAD,'Evidence changed'
print('Issues 24, 25: clean PASS, planted FAIL, repaired PASS, final planted FAIL.')
print('Both marker scripts ran successfully as '+runner+'. Forensic evidence preserved.')
print('Cron and timer persistence planted. No network callbacks or root payload execution.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
