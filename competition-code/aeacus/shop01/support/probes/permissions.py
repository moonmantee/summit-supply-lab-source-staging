"""Metadata plus ACL protection for retained business files."""
import re
import stat
from pathlib import Path
from common import active, protected, protected_reference, result, run

ISSUES = (25,26,27,28,29)

def sudo_paths(output):
    paths=set(re.findall(r'(?m)^(/[^:\n]+): parsed OK$',output))
    paths.update(('/etc/sudoers','/etc/sudoers.d'))
    return paths

def evaluate(issue, d):
    if issue == 25:
        return d.get('protected') is True and d.get('mode') in (0o600,0o640) and d.get('group_ok') is True
    if issue in (26,27,28):
        paths = d.get('protected_paths',[])
        if not paths or not all(paths) or d.get('syntax') is not True: return False
        return issue == 26 or (d.get('running') is True and (issue != 28 or d.get('content_present') is True))
    if issue == 29: return d.get('protected') is True and d.get('running') is True
    return False

def collect(issue):
    if issue == 25:
        import grp
        p = Path('/etc/shadow')
        if not p.exists(): return {'protected':False}
        st = p.stat(); gid = grp.getgrnam('shadow').gr_gid
        return {'protected':protected(p,private=True,group_read=True,expected_gid=gid),
                'mode':stat.S_IMODE(st.st_mode),'group_ok':st.st_gid==gid}
    if issue == 26:
        # visudo enumerates included files, including includes outside sudoers.d.
        output = run(['visudo','-c'])
        paths = sudo_paths(output)
        return {'protected_paths':[protected(p) for p in paths],'syntax':True}
    if issue == 27:
        output = run(['apache2ctl','-t','-D','DUMP_INCLUDES'])
        paths = set(re.findall(r'(?m)^\s*\([^)]*\)\s+(/\S+)\s*$',output))
        required = '/etc/apache2/sites-available/summit-shop.conf'
        paths.add(required)
        return {'protected_paths':[protected_reference(p) for p in paths] + [protected('/etc/apache2')],
                'syntax':result(['apache2ctl','-t']).returncode==0,'running':active('apache2')}
    if issue == 28:
        required = [Path('/var/www/summit')/name for name in ('index.php','order.php','order-history.php')]
        return {'protected_paths':[protected(p) for p in required] + [protected('/var/www/summit')],
                'content_present':all(p.is_file() for p in required),'syntax':result(['apache2ctl','-t']).returncode==0,
                'running':active('apache2')}
    if issue == 29:
        return {'protected':protected('/etc/ssl/private/summit-shop01.key',private=True),'running':active('apache2')}
    return {}

def check(issue): return evaluate(issue,collect(issue))
