"""Install verified probe code only; leave task settings and score history intact."""
import datetime as dt
from pathlib import Path
import shutil
import subprocess
import time
def active(unit): return subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode==0
def ctl(*args): subprocess.run(['systemctl','--user',*args],check=True)
timer=active('summit-check.timer'); portal=active('summit-team-portal.service')
backup=Path('/home/jwang/portal-upgrade-backups')/('i03-probe-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')); backup.mkdir(mode=0o700,parents=True)
saved=[]
try:
    ctl('stop','summit-check.timer')
    until=time.monotonic()+65
    while active('summit-check.service'):
        if time.monotonic()>until: raise RuntimeError('Scoring round still active; retry later.')
        time.sleep(1)
    ctl('stop','summit-team-portal.service')
    for index,base in enumerate(['/home/jwang/summit-portal','/home/jwang/summit-scoring']):
        target=Path(base)/'inject_services.py'; prior=backup/str(index)
        shutil.copy2(target,prior); saved.append((target,prior))
        temp=target.with_suffix('.update'); shutil.copy2('/home/jwang/i03-test-stage/inject_services.py',temp); temp.chmod(0o600); temp.replace(target)
    print('Verified probe installed; backup: '+str(backup))
except Exception:
    for target,prior in reversed(saved): shutil.copy2(prior,target)
    raise
finally:
    errors=[]
    for was_active,unit in [(portal,'summit-team-portal.service'),(timer,'summit-check.timer')]:
        if was_active:
            try: ctl('start',unit)
            except subprocess.CalledProcessError: errors.append(unit)
    if errors: raise RuntimeError('Restart required: '+', '.join(errors))
