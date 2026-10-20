"""Small policy/path helpers for the one-command image builder."""
from pathlib import Path
import re


def wait_scoring_report(report, alive, timeout=60):
    """Caller removes the old report before starting the encrypted runtime."""
    import time
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if not alive(): raise RuntimeError('Encrypted scoring runtime exited before verification')
        try: text=Path(report).read_text()
        except FileNotFoundError: text=''
        if text.rstrip().endswith('</html>'):
            if not re.search(r'\b0 out of 100 points received\b',text) or not re.search(r'\b0 out of 40 scored security issues fixed\b',text):
                raise RuntimeError('Fresh encrypted scoring report differs from 0/100 across 40 checks')
            return
        time.sleep(0.25)
    raise RuntimeError('Timed out waiting for a fresh encrypted scoring report')


def private_phocus(directory,binary):
    """Phocus has a fixed /opt/aeacus path; bind only in a private mount namespace."""
    import os,shutil,signal,subprocess
    directory=Path(directory).resolve()
    shutil.copy2(binary,directory/'phocus')
    (directory/'phocus').chmod(0o700)
    report=directory/'assets/ScoringReport.html'
    report.unlink(missing_ok=True)
    child_code="import os,subprocess,sys; subprocess.run(['/usr/bin/mount','--bind',sys.argv[1],'/opt/aeacus'],check=True); os.chdir('/opt/aeacus'); os.execv('/opt/aeacus/phocus',['/opt/aeacus/phocus'])"
    with (directory/'encrypted-phocus.log').open('wb') as log:
        process=subprocess.Popen(['/usr/bin/unshare','--mount','--propagation','private','/usr/bin/python3','-c',child_code,str(directory)],
                                 cwd=directory,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            wait_scoring_report(report,lambda:process.poll() is None)
        except Exception as error:
            log.flush()
            detail=(directory/'encrypted-phocus.log').read_text(errors='replace')[-2000:]
            raise RuntimeError('Private encrypted-engine verification failed: '+str(error)+'\n'+detail) from error
        finally:
            # Signal only the process group created for this isolated test.
            try: os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=5)

def verified_receipt(path):
    import json
    path=safe_path(path)
    try:
        value=json.loads(path.read_text())
        return isinstance(value,dict) and value.get('verified') is True and value.get('score')==6
    except (OSError,ValueError): return False

def valid_zone_name(name):
    return isinstance(name,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,17}',name))

def unit_state_matches(unit,current,original):
    if any(current.get(key)!=original.get(key) for key in ('LoadState','UnitFileState')): return False
    if unit=='summit-marker.service':
        return current.get('Type')=='oneshot' and current.get('ActiveState') in ('inactive','active','activating')
    return current.get('ActiveState')==original.get('ActiveState')

def choose_finish_backup(base):
    """Preserve failed runs; admit only verified rollback or the known legacy error."""
    base=safe_path(base)
    records=[]
    for number in range(100):
        candidate=base if number==0 else base.with_name(base.name+'-retry'+str(number))
        candidate=safe_path(candidate)
        if not candidate.exists(): return candidate,records
        if not candidate.is_dir(): raise ValueError('Recovery path is not a directory')
        if (candidate/'completed.json').exists(): raise ValueError('Image already completed; refusing to stage again')
        recovered=verified_receipt(candidate/'recovery-verified.json')
        if (candidate/'rollback-failure.txt').exists() and not recovered: raise ValueError('Prior rollback failed; retain records for recovery')
        failure=candidate/'failure.txt'
        index=candidate/'initial/index.json'
        if not failure.is_file() or not index.is_file(): raise ValueError('Incomplete recovery records; refusing replacement')
        message=failure.read_text()
        legacy="INVALID_NAME: Zone 'summit-workstation': name has 18 chars, max is 17" in message
        if not legacy and not recovered and not verified_receipt(candidate/'rollback-verified.json'):
            raise ValueError('Prior rollback has not been verified')
        records.append(candidate)
    raise ValueError('Too many retained attempts')

def validated_snapshot_entries(root,index,targets):
    root=safe_path(root)
    items=index.get('entries',[])
    if [item.get('target') for item in items]!=[str(p) for p in targets]:
        raise ValueError('Saved restoration scope differs; refusing file writes')
    result=[]
    for number,item in enumerate(items):
        target=safe_path(item['target'],allow_leaf_symlink=True)
        saved=safe_path(root/str(number),allow_leaf_symlink=True)
        if item.get('saved')!=str(saved): raise ValueError('Saved copy escapes recovery directory')
        if type(item.get('existed')) is not bool or type(item.get('metadata_only')) is not bool:
            raise ValueError('Invalid saved restoration flags')
        if item['existed'] and not (saved.exists() or saved.is_symlink()): raise ValueError('Saved file is missing')
        result.append((target,saved,item['existed'],item['metadata_only']))
    return result

def safe_path(value,allow_leaf_symlink=False):
    path=Path(value).absolute()
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Symlink parent refused: '+str(path))
    if path.is_symlink() and not allow_leaf_symlink:
        raise ValueError('Symlink target refused: '+str(path))
    return path

def ssh_repair(text):
    if re.search(r'^\s*Match\b',text,re.M|re.I):
        raise ValueError('Contextual SSH rules need separate review')
    keys={'permitrootlogin','permitemptypasswords','allowgroups','allowusers','denyusers','denygroups'}
    lines=[]
    for line in text.splitlines(keepends=True):
        active=line.split('#',1)[0].split()
        if not active or active[0].lower() not in keys: lines.append(line)
    return 'PermitRootLogin no\nPermitEmptyPasswords no\nAllowGroups jwang competitor-recovery linux-workstation-admins@corp.summit.test\n'+''.join(lines)


def restore_entry(target,saved,existed,metadata_only,run,private_trees=()):
    """Restore a bounded entry; leave newly created competitor content intact."""
    import shutil
    target=safe_path(target,allow_leaf_symlink=True)
    saved=Path(saved)
    if existed:
        if target.is_symlink(): target.unlink()
        target.parent.mkdir(parents=True,exist_ok=True)
        if saved.is_dir() and not saved.is_symlink():
            target.mkdir(exist_ok=True)
            if not metadata_only: run(['cp','-a',str(saved)+'/.',target])
            run(['chown','--reference='+str(saved),target])
            run(['chmod','--reference='+str(saved),target])
            run(['chcon','--reference='+str(saved),target])
            run(['setfacl','--set-file=-',target],input=run(['getfacl','-cp',saved])+'\n')
        else: run(['cp','-a',saved,target])
    elif target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            if str(target) in private_trees:
                assert target.stat().st_uid==0 and target.stat().st_mode & 0o077==0
                shutil.rmtree(target)
            else:
                try: target.rmdir()
                except OSError:
                    if not metadata_only: raise
                    return False
        else: target.unlink()
    return True


def restore_training_identity(original,current,name):
    """Restore only scenario identity changes, preserving concurrent real changes."""
    targets={b'summit-unknown',b'summit-departed',b'summit-employee',b'summit-auditor'}
    old={row.split(b':',1)[0]:row for row in original.splitlines()}
    result=[]; seen=set()
    for row in current.splitlines():
        fields=row.split(b':'); key=fields[0]; seen.add(key)
        if name in ('passwd','shadow') and key in targets:
            row=old.get(key,row)
        elif name in ('group','gshadow') and key==b'wheel':
            wanted=b'summit-employee' in old[key].split(b':')[-1].split(b',')
            members=[x for x in fields[-1].split(b',') if x and x!=b'summit-employee']
            if wanted: members.append(b'summit-employee')
            fields[-1]=b','.join(members); row=b':'.join(fields)
        result.append(row)
    if name in ('passwd','shadow'):
        result.extend(row for key,row in old.items() if key in targets and key not in seen)
    return b'\n'.join(result)+b'\n'
