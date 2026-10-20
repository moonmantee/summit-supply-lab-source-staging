#!/usr/bin/env bash
# Synthetic system trust, disposable training key, and forensic scoring rehearsal.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import base64,hashlib,json,os,pathlib,pwd,re,subprocess,sys,tempfile
sys.path.insert(0,'probes')
import access,scenario,trust
def call(args):
    return subprocess.run(args,text=True,capture_output=True,timeout=45,check=True)
backup=pathlib.Path('/var/backups/summit-trust-key-stage')
anchor=pathlib.Path('/etc/pki/ca-trust/source/anchors/summit-fictional-training.crt')
source=pathlib.Path('training-ca/summit-training-ca.crt')
answer=pathlib.Path('/home/jwang/Desktop/Forensics.txt')
user=pwd.getpwnam('summit-keyuser')
assert user.pw_shell in ('/sbin/nologin','/usr/sbin/nologin'),'Training identity must remain noninteractive'
home=pathlib.Path(user.pw_dir); directory=home/'.ssh'; keys=directory/'authorized_keys'
assert not backup.exists(),'Batch already prepared; recovery backup would be overwritten'
assert not anchor.exists() and not anchor.is_symlink(),'Training anchor already exists'
assert not directory.exists() and not directory.is_symlink(),'Training SSH directory already exists'
for path in (home,anchor.parent,answer):
    assert path.exists() and not path.is_symlink(),'Missing or symlink path: '+str(path)
encoded=re.search(r'-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----',source.read_text(),re.S)
assert encoded is not None,'Invalid certificate'
digest=hashlib.sha256(base64.b64decode(re.sub(r'\s','',encoded.group(1)),validate=True)).hexdigest()
assert digest=='27a1a39bd003d5fc0494e82066570ef74206d4da486c39d946faaba239ba5ebe','Unexpected training CA'
assert trust.check(11),'Synthetic CA already trusted or trust probe unavailable'
assert pathlib.Path('/opt/summit-evidence/systemd-marker.sh').read_bytes()==scenario.PAYLOAD,'Evidence hash differs'
assert not any(scenario.check(i) for i in (17,18,19)),'Forensic answers already completed; refusing overwrite'
original_answers=answer.read_bytes()
backup.mkdir(mode=0o700)
call(['cp','-a',str(answer),str(backup/'Forensics.txt')])
def anchors():
    with tempfile.TemporaryDirectory(prefix='summit-anchor-baseline-') as d:
        path=pathlib.Path(d)/'anchors.pem'
        call(['trust','extract','--filter=ca-anchors','--format=pem-bundle',str(path)])
        certs=re.findall(r'-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----',path.read_text(),re.S)
        assert certs,'Trust extraction empty'
        return {hashlib.sha256(base64.b64decode(re.sub(r'\s','',c),validate=True)).hexdigest() for c in certs}
original_anchors=anchors()
records={}
created_key=False
created_anchor=False
def restore():
    global created_anchor,created_key
    if created_anchor:
        assert anchor.is_file() and not anchor.is_symlink() and anchor.read_bytes()==source.read_bytes(),'Training anchor changed; refusing removal'
        anchor.unlink(); created_anchor=False
        call(['update-ca-trust','extract'])
    if created_key:
        assert not keys.is_symlink() and keys.read_bytes()==public_key,'Training key changed; refusing removal'
        keys.unlink(); directory.rmdir(); created_key=False
    call(['cp','-a',str(backup/'Forensics.txt'),str(answer)])
try:
    # A disposable signing key never leaves the private temporary directory.
    with tempfile.TemporaryDirectory(prefix='summit-disposable-key-') as d:
        private=pathlib.Path(d)/'training'
        call(['ssh-keygen','-q','-t','ed25519','-N','','-C','fictional-training-key','-f',str(private)])
        public_key=pathlib.Path(str(private)+'.pub').read_bytes()
    directory.mkdir(mode=0o700); os.chown(directory,user.pw_uid,user.pw_gid)
    created_key=True
    keys.write_bytes(public_key); keys.chmod(0o600); os.chown(keys,user.pw_uid,user.pw_gid)
    call(['restorecon','-R',str(directory)])
    records['key_clean']=access.check(8); assert records['key_clean'],'Secure key permissions did not pass'
    directory.chmod(0o777); keys.chmod(0o666)
    records['key_planted']=access.check(8); assert not records['key_planted'],'Insecure key permissions falsely passed'
    directory.chmod(0o700); keys.chmod(0o600)
    records['key_repaired']=access.check(8); assert records['key_repaired'],'Key repair failed'
    directory.chmod(0o777); keys.chmod(0o666)
    records['key_final_planted']=access.check(8); assert not records['key_final_planted'],'Final insecure permissions falsely passed'
    records['trust_clean']=trust.check(11); assert records['trust_clean']
    anchor.write_bytes(source.read_bytes()); anchor.chmod(0o644); created_anchor=True
    call(['restorecon',str(anchor)]); call(['update-ca-trust','extract'])
    records['trust_planted']=trust.check(11); assert not records['trust_planted'],'Trusted training CA falsely passed'
    assert original_anchors<=anchors(),'Existing trust anchors were lost'
    anchor.unlink(); created_anchor=False; call(['update-ca-trust','extract'])
    records['trust_repaired']=trust.check(11); assert records['trust_repaired'],'Trust repair failed'
    assert anchors()==original_anchors,'Original trust did not return'
    anchor.write_bytes(source.read_bytes()); anchor.chmod(0o644); created_anchor=True
    call(['restorecon',str(anchor)]); call(['update-ca-trust','extract'])
    records['trust_final_planted']=trust.check(11); assert not records['trust_final_planted']
    assert original_anchors<=anchors(),'Existing trust anchors were lost'
    # Exercise forensic positive and negative states without exposing answers
    # in console output or leaving the answer key on the participant desktop.
    answer.write_text(''.join('Q%d = %s\n'%scenario.ANSWERS[i] for i in (17,18,19)))
    records['forensics_correct']={str(i):scenario.check(i) for i in (17,18,19)}
    assert all(records['forensics_correct'].values()),'Correct forensic answers failed'
    answer.write_text('Q1 = incorrect\nQ2 = incorrect\nQ3 = incorrect\n')
    records['forensics_incorrect']={str(i):scenario.check(i) for i in (17,18,19)}
    assert not any(records['forensics_incorrect'].values()),'Incorrect forensic answers passed'
    call(['cp','-a',str(backup/'Forensics.txt'),str(answer)])
    assert answer.read_bytes()==original_answers,'Participant answer file did not restore'
    records['forensics_final']={str(i):scenario.check(i) for i in (17,18,19)}
    assert not any(records['forensics_final'].values()),'Final unanswered forensic questions passed'
except BaseException:
    restore()
    raise
(backup/'rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
(backup/'rehearsal.json').chmod(0o600)
print('Issues 8, 11: clean PASS, planted FAIL, repaired PASS, final planted FAIL.')
print('Forensics 17-19: correct answers PASS, incorrect answers FAIL, original unanswered file restored.')
print('Existing CA anchors preserved. Disposable SSH private key discarded. Training account remains noninteractive.')
PY
bash /home/jwang/aeacus-setup/validate-probes.sh
