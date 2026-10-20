"""Presence and activation checks for harmless named training fixtures."""
import re
from pathlib import Path
from common import ProbeError, read, unit

ISSUES = (38,39,40)
UNIT = 'summit-shop-marker.service'
EXECUTABLE = '/opt/summit-shop-training/suid-marker'

def evaluate(issue,d):
    if issue == 38: return d.get('references_absent') is True
    if issue == 39:
        u = d.get('unit',{})
        return d.get('references_absent') is True and u.get('ActiveState') in ('inactive','failed') and (
            u.get('LoadState') == 'not-found' or (u.get('LoadState') == 'loaded' and u.get('UnitFileState') in ('disabled','masked')))
    if issue == 40: return d.get('present') is False or (d.get('present') is True and type(d.get('mode')) is int and not d['mode'] & 0o4000)
    return False

def contains(paths, tokens):
    for p in paths:
        if p.is_symlink():
            if any(t in str(p.resolve()) or t in p.name for t in tokens): return True
        elif p.is_file():
            if any(t in read(p) for t in tokens): return True
    return False

def collect(issue):
    if issue == 38:
        paths = [Path('/etc/crontab')]
        for folder in ('/etc/cron.d','/var/spool/cron/crontabs'):
            root = Path(folder)
            if root.exists(): paths.extend(root.iterdir())
        return {'references_absent':not contains(paths,('summit-shop-cron','/opt/summit-shop-training/cron-marker.sh'))}
    if issue == 39:
        paths = []
        for folder in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system'):
            root=Path(folder)
            if root.exists(): paths.extend(root.rglob('*'))
        return {'unit':unit(UNIT),'references_absent':not contains(paths,(UNIT,'/opt/summit-shop-training/systemd-marker.sh'))}
    if issue == 40:
        p = Path(EXECUTABLE)
        return {'present':p.exists(),'mode':p.stat().st_mode if p.exists() else None}
    raise ProbeError('Unsupported persistence objective')

def check(issue): return evaluate(issue,collect(issue))
