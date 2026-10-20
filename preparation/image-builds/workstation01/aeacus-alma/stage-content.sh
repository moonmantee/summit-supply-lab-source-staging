#!/usr/bin/env bash
# First reversible weakness batch: synthetic files and original offline game.
# Does not change services, authentication, network settings, or production scorer.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname -s) == workstation01 ]] || { echo 'Run as root on workstation01.'; exit 1; }
cd /home/jwang/aeacus-setup
python3 - <<'PY'
import hashlib,json,pathlib,sys
sys.path.insert(0,'probes')
import scenario
root=pathlib.Path('scenario-assets')
hashes=json.loads(pathlib.Path('artifact-hashes.json').read_text())
targets={
 'fictional-credentials.txt':pathlib.Path('/home/jwang/Downloads/summit-fictional-credentials.txt'),
 'personal-media.zip':pathlib.Path('/home/jwang/Downloads/summit-personal-media.zip'),
 'offline-game.py':pathlib.Path('/usr/local/share/summit-games/offline-game.py'),
 'summit-offline-game.desktop':pathlib.Path('/home/jwang/Desktop/summit-offline-game.desktop'),
}
ids=(27,28,34)
# All preconditions are checked before the first mutation.
for name,path in targets.items():
    assert not path.exists() and not path.is_symlink(),'Target exists: '+str(path)
    assert path.parent.is_dir() and not path.parent.is_symlink(),'Missing/unsafe parent: '+str(path.parent)
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==hashes[name],'Asset mismatch: '+name
assert all(scenario.check(i) for i in ids),'Clean-state checks do not pass; no files planted'
records={'clean':{str(i):True for i in ids}}
created=[]
def install():
    import os,pwd
    user=pwd.getpwnam('jwang')
    for name,path in targets.items():
        # Exclusive creation prevents overwriting an unrelated file.
        with path.open('xb') as f:
            f.write((root/name).read_bytes())
        created.append((name,path))
        path.chmod(0o644)
        if str(path).startswith('/home/jwang/'):
            os.chown(path,user.pw_uid,user.pw_gid)
def remove_owned():
    for name,path in reversed(created):
        assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==hashes[name],'Changed artifact; refusing cleanup: '+str(path)
        path.unlink()
    created.clear()
try:
    install()
    records['planted']={str(i):scenario.check(i) for i in ids}
    assert not any(records['planted'].values()),'Planted checks incorrectly award credit'
    remove_owned()
    records['repaired']={str(i):scenario.check(i) for i in ids}
    assert all(records['repaired'].values()),'Clean repair checks failed'
    install()
    records['final_planted']={str(i):scenario.check(i) for i in ids}
    assert not any(records['final_planted'].values()),'Final planted checks incorrectly award credit'
except BaseException:
    remove_owned()
    raise
pathlib.Path('/var/tmp/summit-content-rehearsal.json').write_text(json.dumps(records,indent=2)+'\n')
pathlib.Path('/var/tmp/summit-content-rehearsal.json').chmod(0o600)
print('Issues 27, 28, 34 verified: clean PASS, planted FAIL, repaired PASS, final planted FAIL.')
print('Three file-based weaknesses planted. Production scoring remains unchanged.')
PY
