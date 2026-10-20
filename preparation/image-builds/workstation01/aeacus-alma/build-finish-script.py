"""Build the single distributable; no guest changes are made here."""
import ast,base64,hashlib,io,json,re,tarfile,textwrap
from pathlib import Path

ROOT=Path(__file__).parent
FILES=['finish_workstation.py','finish_helpers.py','auth_policy.py','application_stage.py',
       'test_finish_helpers.py','test_auth_policy.py','test_application_stage.py',
       'pam_runner.py','probe-validation-scoring.conf','competition-ReadMe.conf',
       'competition-manifest.json','artifact-hashes.json']
FILES += [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'probes').glob('*.py'))]

def build():
    worker=ast.parse((ROOT/'finish_workstation.py').read_text())
    zone=next(n.value.value for n in worker.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ZONE' for t in n.targets))
    assert re.fullmatch(r'[A-Za-z0-9_-]{1,17}',zone),'Firewalld zone name exceeds installed limits'
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as archive:
        for name in FILES:
            data=(ROOT/name).read_bytes().replace(b'\r\n',b'\n')
            if name.endswith('.py'): ast.parse(data,filename=name,feature_version=(3,9))
            item=tarfile.TarInfo(name); item.size=len(data); item.mode=0o600
            archive.addfile(item,io.BytesIO(data))
    payload=buf.getvalue(); digest=hashlib.sha256(payload).hexdigest()
    manifest=json.loads((ROOT/'competition-manifest.json').read_text())
    assert len(manifest['issues'])==40 and sum(i['points'] for i in manifest['issues'])==100
    conf=(ROOT/'probe-validation-scoring.conf').read_text()
    assert len(re.findall(r'^\[\[check\]\]$',conf,re.M))==40
    assert sum(map(int,re.findall(r'^points = (\d+)$',conf,re.M)))==100
    code='''#!/usr/bin/env bash
# One-command organizer finish for the pinned workstation01 AlmaLinux 9.8 image.
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo "Run this file with sudo bash." >&2; exit 1; }
unset SUMMIT_FORENSICS_ROOT PYTHONPATH PYTHONHOME
export LC_ALL=C
work=$(mktemp -d /var/tmp/summit-finish.XXXXXXXX)
chmod 700 "$work"
printf 'Private payload directory: %s\\n' "$work"
base64 --decode > "$work/payload.tgz" <<'SUMMIT_PAYLOAD'
__PAYLOAD__
SUMMIT_PAYLOAD
/usr/bin/python3 - "$work" <<'SUMMIT_EXTRACT'
import hashlib,io,os,pathlib,sys,tarfile
root=pathlib.Path(sys.argv[1])
assert str(root).startswith('/var/tmp/summit-finish.') and not root.is_symlink()
assert root.stat().st_uid==0 and root.stat().st_mode & 0o077==0
blob=(root/'payload.tgz').read_bytes()
assert hashlib.sha256(blob).hexdigest()=='__SHA256__','Payload integrity check failed'
with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
    for item in archive.getmembers():
        path=pathlib.PurePosixPath(item.name)
        assert item.isfile() and not path.is_absolute() and '..' not in path.parts
        assert item.size<2_000_000
        destination=root/path
        destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with destination.open('xb') as output: output.write(archive.extractfile(item).read())
        destination.chmod(0o600)
print('Bundled payload hash and extraction verified.')
SUMMIT_EXTRACT
if ! /usr/bin/python3 -m unittest discover -s "$work/probes" -p 'test_*.py'; then
  echo "Probe tests failed; no system changes made. Payload retained: $work" >&2
  exit 1
fi
if ! /usr/bin/python3 -m unittest discover -s "$work" -p 'test_*.py'; then
  echo "Controller helper tests failed; no system changes made. Payload retained: $work" >&2
  exit 1
fi
if /usr/bin/python3 "$work/finish_workstation.py" "$work"; then
  /usr/bin/python3 - "$work" <<'SUMMIT_CLEANUP'
import pathlib,shutil,sys
root=pathlib.Path(sys.argv[1])
assert str(root).startswith('/var/tmp/summit-finish.') and not root.is_symlink()
assert root.stat().st_uid==0 and root.stat().st_mode & 0o077==0
shutil.rmtree(root)
SUMMIT_CLEANUP
else
  echo "Finish stopped. Private diagnostics and payload retained: $work" >&2
  exit 1
fi
'''
    code=code.replace('__PAYLOAD__','\n'.join(textwrap.wrap(base64.b64encode(payload).decode(),76))).replace('__SHA256__',digest)
    destination=ROOT/'finish-workstation01.sh'; destination.write_text(code,encoding='utf-8',newline='\n')
    report={'script':destination.name,'payload_sha256':digest,'script_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'bundled_files':FILES,'checks':40,'points':100,'guest_execution_verified':False}
    (ROOT/'finish-script-build.json').write_text(json.dumps(report,indent=2)+'\n',newline='\n')
    print('Built '+destination.name+'; '+str(len(FILES))+' files; 40 checks / 100 points. Guest execution pending.')

if __name__=='__main__': build()
