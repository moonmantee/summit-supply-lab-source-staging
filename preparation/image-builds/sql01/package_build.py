"""Generate manifest, scoring config and one LF-only privileged entry point."""
from pathlib import Path
import base64,hashlib,io,json,zipfile
ROOT=Path(__file__).resolve().parent
ROWS=[
 ('Application Security','MariaDB LOCAL INFILE disabled','Runtime and native persistent local_infile disabled'),
 ('User Auditing','Unauthorized database account removed','training_vendor absent, required SQL identities retained'),
 ('Application Security','Shop global file privilege removed','No effective FILE grant, including inherited roles'),
 ('Application Security','Forum cross-database access removed','No effective forum_app privileges on shop data'),
 ('Application Security','Direct root SSH disabled','Effective PermitRootLogin no'),
 ('Application Security','Empty-password SSH disabled','Effective PermitEmptyPasswords no; no usable empty-password user planted'),
 ('Application Security','SSH X11 forwarding disabled','Effective X11Forwarding no'),
 ('User Auditing','Employee excess administrator access removed','No excess effective sudo authorization for summit_employee'),
 ('User Auditing','Contractor excess administrator access removed','No excess effective sudo authorization for summit_contractor'),
 ('Application Security','Operational backup permissions repaired','Retained synthetic backup owned by root, restrictive mode and ACL'),
 ('Malware','Unauthorized cron marker removed','Exact cron activation and live payload absent'),
 ('Malware','Unauthorized systemd marker removed','Timer/service disabled across activation paths and live payload absent'),
 ('Prohibited Files','Fictional plaintext credentials removed','Designated marker absent from stated shared and home scope'),
 ('Prohibited Files','Unauthorized personal media removed','Designated marker absent from stated shared and home scope'),
 ('Service Auditing','Discovery activation disabled','Avahi service/socket inactive and disabled or masked'),
 ('Service Auditing','Printing activation disabled','CUPS service/socket/path inactive and disabled or masked'),
 ('Local Policy','Persistent logging restored','Native Storage=persistent and journald has persistent journal open'),
 ('Application Security','SSH authentication attempt limit repaired','Effective MaxAuthTries between one and three'),
 ('Application Security','SSH agent forwarding disabled','Effective AllowAgentForwarding no'),
 ('Application Security','SSH TCP forwarding disabled','Effective AllowTcpForwarding no'),
 ('Application Security','SSH user environment injection disabled','Effective PermitUserEnvironment no'),
 ('Local Policy','Verbose SSH authentication logging restored','Effective LogLevel VERBOSE'),
 ('Defensive Countermeasures','Hard-link protection enabled','Effective runtime and native boot configuration fs.protected_hardlinks >=1'),
 ('Defensive Countermeasures','Symbolic-link protection enabled','Effective runtime and native boot configuration fs.protected_symlinks >=1'),
 ('Defensive Countermeasures','Kernel pointer disclosure restricted','Effective runtime and native boot configuration kernel.kptr_restrict >=1'),
 ('Defensive Countermeasures','Kernel message access restricted','Effective runtime and native boot configuration kernel.dmesg_restrict >=1'),
 ('Uncategorized Operating System Settings','Shell startup permissions repaired','Retained inert profile script root-owned and no ordinary-user write ACL'),
 ('Forensics Questions','Forensic account attribution answered','Only individual Answer section matches private answer'),
 ('Forensics Questions','Forensic timer attribution answered','Only individual Answer section matches private answer'),
 ('Forensics Questions','Forensic payload fingerprint answered','Only individual Answer section matches private answer')]
def main():
    issues=[]
    for i,(category,message,repair) in enumerate(ROWS,1):
        issues.append({'id':i,'category':category,'points':6 if i>=28 else 4 if i==4 else 3,'message':message,
                       'planted_state':'Policy-inconsistent opposite of repair; question answers blank' if i<28 else 'Blank individual answer',
                       'repair':repair,'probe':'/usr/bin/python3 /opt/summit-sql01/probes.py '+str(i),
                       'dependencies':['mariadb','ssh','sssd','root-readable private metadata'],
                       'preserve':['shop/forum data and own-schema app rights','jwang access','domain trust','approved users'],
                       'recovery':'Unique /var/backups/summit-sql01-competition-* native baseline; scoped automatic rollback and independent prebuild VM snapshot',
                       'status':'prepared','evidence':[]})
    assert len(issues)==30 and sum(i['points'] for i in issues)==100
    manifest={'machine':'sql01','os':'Linux Mint 22.3 Zena','role':'MariaDB shop/forum server','domain':'corp.summit.test',
              'approved_users':['jwang','alex.admin@corp.summit.test','taylor.admin@corp.summit.test'],
              'required_ports':[22,3306],'business_data':['summit_shop','forum'],
              'management':'Strict pinned-key SSH via range-fw, plus user-confirmed guest console',
              'recovery_snapshot':'SQL01-before-competition-20261004 (creation verification recorded in STATUS.md)',
              'scoring':{'engine':'Aeacus/Phocus 2.1.1','count':30,'points':100,'start':0,'solution':100,'restored':0},
              'status':'prepared','guest_rehearsals':'pending','manual_acceptance':'pending','export':'pending','issues':issues}
    (ROOT/'competition-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',newline='\n')
    config='name = "summit-sql01-competition"\ntitle = "Summit SQL01 Security"\nos = "Linux Mint 22.3"\nuser = "jwang"\nversion = "2.1.1"\nlocal = true\nshell = false\n'
    for issue in issues:
        config+='\n[[check]]\nmessage = '+json.dumps(issue['message'])+'\npoints = '+str(issue['points'])+'\n[[check.pass]]\ntype = "CommandOutput"\ncmd = '+json.dumps(issue['probe'])+'\nvalue = "PASS"\n'
    (ROOT/'scoring.conf').write_text(config,newline='\n')
    data=io.BytesIO()
    names=('contract.py','probes.py','build_sql01.py','test_contract.py','scoring.conf','README.html','competition-manifest.json','aeacus-linux-v2.1.1.zip')
    with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            content=(ROOT/name).read_bytes() if name!='aeacus-linux-v2.1.1.zip' else (ROOT/name).read_bytes()
            if name.endswith(('.py','.conf','.html','.json')): content=content.replace(b'\r\n',b'\n')
            archive.writestr(name,content)
    blob=data.getvalue(); digest=hashlib.sha256(blob).hexdigest()
    header='''#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 && $(hostname -s) == sql01 ]] || { echo 'Run with sudo on sql01 only.'; exit 1; }
umask 077
python3 - <<'SQL01_PAYLOAD'
import base64,hashlib,io,os,pathlib,subprocess,tempfile,zipfile
blob=base64.b64decode('''+repr(base64.b64encode(blob).decode())+''')
assert hashlib.sha256(blob).hexdigest()=='''+repr(digest)+''', 'Payload checksum mismatch'
directory=pathlib.Path(tempfile.mkdtemp(prefix='summit-sql01-payload-',dir='/var/backups'))
directory.chmod(0o700)
expected='''+repr(set(names))+'''
with zipfile.ZipFile(io.BytesIO(blob)) as archive:
    assert set(archive.namelist())==expected and len(archive.namelist())==len(expected), 'Payload member mismatch'
    for member in archive.infolist():
        assert member.filename in expected and member.file_size<120*1024**2, 'Unsafe payload'
        target=directory/member.filename
        target.write_bytes(archive.read(member)); target.chmod(0o600)
print('Private verified payload: '+str(directory),flush=True)
subprocess.run(['python3','-m','unittest','test_contract','-v'],cwd=directory,check=True)
subprocess.run(['python3',str(directory/'build_sql01.py')],cwd=directory,check=True)
SQL01_PAYLOAD
'''
    (ROOT/'make-sql01-competition.sh').write_text(header,newline='\n')
    print('Packaged 30 checks / 100 points. SHA256 '+hashlib.sha256(header.encode()).hexdigest())
if __name__=='__main__': main()
