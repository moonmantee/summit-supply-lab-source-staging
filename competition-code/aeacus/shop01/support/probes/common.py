"""Bounded read-only helpers. Errors never become successful remediation."""
import os
import re
import stat
import subprocess
from pathlib import Path

class ProbeError(Exception):
    pass

def result(argv, timeout=12):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, 'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ProbeError(type(e).__name__) from None

def run(argv, timeout=12):
    p = result(argv, timeout)
    if p.returncode:
        raise ProbeError('Command unsuccessful')
    return p.stdout

def read(path):
    try:
        return Path(path).read_text()
    except (OSError, UnicodeError) as e:
        raise ProbeError(type(e).__name__) from None

def setting(text, key):
    values = []
    for line in text.splitlines():
        parts = re.split(r'[=\s]+', line.split('#',1)[0].strip(), maxsplit=1)
        if len(parts) == 2 and parts[0].lower() == key.lower():
            values.append(parts[1].strip())
    return values[0] if len(values) == 1 else None

def sudo_denied(code, text, user):
    if code not in (0,1) or re.search(r'\([^\n]*\)|NOPASSWD:|Commands:|Sudoers entry:', text):
        return False
    return bool(re.search(r'(?m)^User ' + re.escape(user) + r' is not allowed to run sudo on shop01\.$', text))

def acl_safe(text, private=False, group_read=False):
    entries = {}
    for raw in text.splitlines():
        line = raw.split('#',1)[0].strip()
        if not line: continue
        parts = line.split(':')
        if parts[0] == 'default':
            key = ':'.join(parts[:-1])
        else:
            key = ':'.join(parts[:-1])
        if len(parts) not in (3,4) or not re.fullmatch('[r-][w-][x-]', parts[-1]):
            return False
        entries[key] = parts[-1]
    if not all(k in entries for k in ('user:', 'group:', 'other:')):
        return False
    for key, permissions in entries.items():
        default = key.startswith('default:')
        base = key[8:] if default else key
        if base in ('user:', 'mask:'): continue
        mask = entries.get(('default:' if default else '') + 'mask:', 'rwx')
        effective = ''.join(c if c in mask else '-' for c in permissions) if base.startswith(('group:', 'user:')) else permissions
        if 'w' in effective: return False
        if private and (not (base == 'group:' and group_read)) and ('r' in effective or 'x' in effective):
            return False
    return True

def protected(path, private=False, group_read=False, expected_gid=None):
    path = Path(path)
    try:
        if not path.exists() or path.is_symlink(): return False
        st = path.stat()
        if st.st_uid != 0: return False
        if expected_gid is not None and st.st_gid != expected_gid: return False
        if st.st_mode & 0o022: return False
        if private and st.st_mode & (0o007 if group_read else 0o077): return False
        if not acl_safe(run(['getfacl','-cpn',str(path)]), private, group_read): return False
        for ancestor in path.absolute().parents:
            a = ancestor.stat()
            if ancestor.is_symlink() or a.st_uid != 0 or a.st_mode & 0o022: return False
            if not acl_safe(run(['getfacl','-cpn',str(ancestor)])): return False
        return True
    except FileNotFoundError:
        return False

def active(name):
    p = result(['systemctl','is-active',name])
    if p.returncode == 0 and p.stdout.strip() == 'active': return True
    if p.returncode in (3,4): return False
    raise ProbeError('Unknown service state')


def protected_reference(path):
    """Check a root-owned active include link, its parents, and target."""
    p=Path(path)
    if not p.exists(): return False
    if p.is_symlink():
        if p.lstat().st_uid!=0 or not protected(p.parent): return False
        return protected(p.resolve())
    return protected(p)

def unit(name):
    p = result(['systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','UnitFileState'])
    data = dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
    if not data or (p.returncode and data.get('LoadState') != 'not-found'):
        raise ProbeError('Unusable unit state')
    return data
