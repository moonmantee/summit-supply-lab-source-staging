"""Pure acceptance rules shared by SQL01 probes and its builder."""
import re

def answer(text):
    sections = re.split(r'^Answer:\s*$', text, flags=re.M)
    if len(sections) != 2: raise ValueError('Expected one Answer section')
    return sections[1].strip().casefold()

def require_matrix(states, expected):
    if len(states) != 30 or any(s != expected for s in states):
        raise RuntimeError('Expected thirty '+expected+' results; observed '+repr(states))

def parse_native(text):
    result = {}
    for line in text.splitlines():
        if not line.strip(): continue
        parts = line.split(None,1)
        if len(parts) != 2: raise ValueError('Malformed native setting')
        result.setdefault(parts[0].lower(), []).append(parts[1].strip())
    return result

def require_report(html, score):
    points = re.search(r'(\d+) out of (\d+) points received',html)
    issues = re.search(r'(\d+) out of (\d+) scored security issues fixed',html)
    if (not html.rstrip().endswith('</html>') or not points or not issues
        or tuple(map(int,points.groups())) != (score,100)
        or tuple(map(int,issues.groups())) != (30 if score==100 else 0,30)):
        raise ValueError('Missing/partial/wrong thirty-check score report')

def backup_acl_ok(uid,mode,acl,content_ok,gid=0):
    if uid != 0 or mode & 0o037 or not content_ok: return False
    if gid!=0 and mode & 0o070: return False
    for line in acl.splitlines():
        line=line.split('#',1)[0].strip()
        if not line: continue
        parts=line.split(':')
        if len(parts)!=3: return False
        if parts[0] in ('user','group') and parts[1] and parts[2] != '---': return False
        if parts[0]=='other' and parts[2]!='---': return False
    return True

def unit_safe(state):
    if 'ActiveState' not in state or 'UnitFileState' not in state: raise ValueError('Unreadable unit state')
    return state['ActiveState'] in ('inactive','failed') and state['UnitFileState'] in ('disabled','masked','masked-runtime')
