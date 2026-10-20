"""Local identities and effective SSH policy; never prints password hashes."""
import fnmatch
import json
import os
import re
import stat
from pathlib import Path
from common import ProbeError, active, acl_safe, protected, read, result, run, setting, sudo_denied

ISSUES = (1,2,3,4,5,6,11,12,13,14,15,16)
EDITOR = 'summit_editor'
EMPLOYEE = 'summit_employee'
SSH_USERS = {'jwang', EDITOR}
SOURCES = ('10.77.10.50','10.77.10.1','10.77.30.1','10.77.70.10')

def system_identity(record):
    return (int(record[2]) < 1000 or (record[0]=='nobody' and record[2]=='65534')) and record[6].endswith(('nologin','false'))

def users(text):
    parsed = {}
    for line in text.splitlines():
        fields = line.split(':')
        if len(fields) != 7 or not fields[2].isdigit() or not fields[3].isdigit():
            raise ProbeError('Malformed local identity data')
        if fields[0] in parsed: raise ProbeError('Duplicate identity')
        parsed[fields[0]] = fields
    return parsed

def active_password_hash(value):
    # Ubuntu's SHA-crypt and yescrypt formats; locked/invalid strings are not
    # usable credentials merely because they begin with a dollar sign.
    sha=re.fullmatch(r'\$([56])\$(?:rounds=([0-9]+)\$)?([./A-Za-z0-9]{1,16})\$([./A-Za-z0-9]+)',value)
    if sha:
        return (len(sha[4])==(86 if sha[1]=='6' else 43) and
                (sha[2] is None or 1000<=int(sha[2])<=999999999))
    return re.fullmatch(r'\$y\$[./A-Za-z0-9]{1,32}\$[./A-Za-z0-9]{1,86}\$[./A-Za-z0-9]{43}',value) is not None

def ssh_list(text,key):
    # sshd -T emits one line per element for list-valued directives.
    values=[]
    for line in text.splitlines():
        parts=line.split('#',1)[0].split()
        if parts and parts[0].lower()==key.lower(): values.extend(parts[1:])
    return values

def evaluate(issue, d):
    if issue == 1: return d.get('contractor_absent') is True and d.get('recovery_present') is True
    if issue == 2:
        u = users(d.get('users',''))
        return 'root' in u and int(u['root'][2]) == 0 and {n for n,r in u.items() if int(r[2]) == 0} == {'root'}
    if issue in (3,4):
        return d.get('exists') is True and bool(d.get('groups')) and 'sudo' not in d['groups'] and (issue != 4 or d.get('system_identity') is True)
    if issue == 5: return d.get('exists') is True and d.get('sudo_denied') is True
    if issue == 6: return all(d.get(k) is True for k in ('exists','active_hash','changed_hash','usable'))
    if issue == 11: return d.get('exists') is True and d.get('usable') is True and d.get('active_hash') is True and type(d.get('max_age')) is int and 0 < d['max_age'] <= 90
    if issue in (12,13,14):
        configs = d.get('configs',[])
        if d.get('running') is not True or not configs: return False
        if issue in (12,13):
            key = 'permitrootlogin' if issue == 12 else 'permitemptypasswords'
            return all(setting(c,key) == 'no' for c in configs)
        for c in configs:
            allowed = ssh_list(c, 'allowusers')
            if not allowed or set(allowed) != SSH_USERS: return False
            if setting(c,'authorizedkeyscommand') != 'none': return False
            denied = ssh_list(c,'denyusers')
            if any(fnmatch.fnmatch(u, pattern) for u in SSH_USERS for pattern in denied): return False
            # Restrictive group clauses need explicit audit rather than assume that
            # AllowUsers alone grants access to both approved administrators.
            if ssh_list(c,'allowgroups') or ssh_list(c,'denygroups'): return False
        return True
    if issue == 15:
        return all(d.get(k) is True for k in ('exists','running','unauthorized_absent','approved_present','sources_checked'))
    if issue == 16:
        return all(d.get(k) is True for k in ('exists','running','approved_present','permissions_safe'))
    return False

def private_metadata():
    p = Path('/var/lib/summit-shop01/private.json')
    st = p.lstat()
    if p.is_symlink() or st.st_uid != 0 or st.st_mode & 0o077:
        raise ProbeError('Unsafe scenario metadata')
    data = json.loads(read(p))
    if not isinstance(data,dict): raise ProbeError('Invalid scenario metadata')
    return data

def ssh_configs(user):
    return [run(['/usr/sbin/sshd','-T','-C',f'user={user},host=shop01,addr={source}']) for source in SOURCES]

def key_blobs(text):
    return set(re.findall(r'(?:^|\s)(?:ssh-(?:rsa|ed25519)|ecdsa-sha2-\S+|sk-\S+)\s+(\S+)',text,re.M))

def key_paths(user, home):
    configurations = ssh_configs(user)
    paths = set()
    for c in configurations:
        if setting(c,'authorizedkeyscommand') != 'none': raise ProbeError('External key source requires inspection')
        configured = setting(c,'authorizedkeysfile')
        if not configured or configured == 'none': raise ProbeError('No approved key source')
        for raw in configured.split():
            expanded = raw.replace('%h',home).replace('%u',user).replace('%%','%')
            if '%' in expanded: raise ProbeError('Unsupported key path token')
            p = Path(expanded)
            paths.add(p if p.is_absolute() else Path(home)/p)
    return paths

def collect(issue):
    local = users(read('/etc/passwd'))
    if issue == 1: return {'contractor_absent':'contractor_lab' not in local,'recovery_present':'jwang' in local}
    if issue == 2: return {'users':read('/etc/passwd')}
    target = 'nobody' if issue == 4 else EDITOR if issue in (15,16) else 'summit_support' if issue == 5 else EMPLOYEE
    exists = target in local
    if issue in (3,4):
        return {'exists':exists,'groups':run(['id','-nG',target]).split() if exists else [],
                'system_identity':exists and system_identity(local[target])}
    if issue == 5:
        if not exists: return {'exists':False}
        p = result(['sudo','-ll','-U',target])
        return {'exists':True,'sudo_denied':sudo_denied(p.returncode,p.stdout+p.stderr,target)}
    if issue in (6,11):
        if not exists: return {'exists':False}
        shadow = [l.split(':') for l in read('/etc/shadow').splitlines() if l.split(':',1)[0] == target]
        if len(shadow) != 1 or len(shadow[0]) != 9: raise ProbeError('Invalid shadow record')
        record = shadow[0]
        usable = local[target][6] not in ('/usr/sbin/nologin','/bin/false','/sbin/nologin') and record[7] in ('','-1')
        if issue == 11:
            return {'exists':True,'max_age':int(record[4]) if record[4] else -1,'usable':usable,'active_hash':active_password_hash(record[1])}
        original = private_metadata().get('planted_employee_hash')
        if not isinstance(original,str) or not active_password_hash(original): raise ProbeError('Missing original credential reference')
        return {'exists':True,'active_hash':active_password_hash(record[1]),'changed_hash':record[1] != original,'usable':usable}
    if issue in (12,13,14):
        principals = ('root',) if issue == 12 else ('jwang',EDITOR,'contractor_lab')
        return {'running':active('ssh'),'configs':[c for user in principals for c in ssh_configs(user)]}
    if issue in (15,16):
        if not exists: return {'exists':False}
        data = private_metadata(); approved = data.get('approved_key_blob'); planted = data.get('unauthorized_key_blob')
        if not approved or not planted: raise ProbeError('Missing key fixture references')
        home = local[target][5]; paths = key_paths(target,home)
        blobs = set()
        for p in paths:
            if p.exists(): blobs.update(key_blobs(read(p)))
        observed = {'exists':True,'running':active('ssh'),'unauthorized_absent':planted not in blobs,
                    'approved_present':approved in blobs,'sources_checked':True}
        if issue == 16:
            p = Path(home)/'.ssh'; key = p/'authorized_keys'; uid = int(local[target][2]); safe = protected(Path(home).parent)
            for candidate, mode in [(Path(home),None),(p,0o700)] + [(keypath,0o600) for keypath in paths]:
                if candidate.is_symlink(): safe=False; continue
                if candidate.exists():
                    st = candidate.stat()
                    if st.st_uid not in (uid,0) or st.st_mode & 0o022 or (mode is not None and stat.S_IMODE(st.st_mode) != mode): safe=False
                    if not acl_safe(run(['getfacl','-cpn',str(candidate)]),private=(mode is not None)): safe=False
                elif candidate not in paths: safe=False
                # Alternate key sources require all lexical parent paths to be
                # protected; recognize the owned editor home/.ssh separately.
                for parent in candidate.absolute().parents:
                    if parent not in (Path(home),p) and not protected(parent): safe=False
            observed['permissions_safe'] = safe
        return observed
    raise ProbeError('Unsupported access objective')

def check(issue): return evaluate(issue, collect(issue))
