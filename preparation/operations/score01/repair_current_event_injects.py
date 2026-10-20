"""Preserve the running event and seed fresh tasks from the approved template."""
from contextlib import closing
import datetime as dt
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

portal=Path('/home/jwang/summit-portal'); score=Path('/home/jwang/summit-scoring'); stage=Path('/home/jwang/inject-reset-repair')
def active(unit): return subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode==0
def ctl(*args): subprocess.run(['systemctl','--user',*args],check=True)
timer=active('summit-check.timer'); running=active('summit-team-portal.service')
backup=Path('/home/jwang/portal-upgrade-backups')/('reset-inject-repair-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')); backup.mkdir(mode=0o700,parents=True)
saved=[]; db_ready=False
try:
    ctl('stop','summit-check.timer')
    until=time.monotonic()+65
    while active('summit-check.service'):
        if time.monotonic()>until: raise RuntimeError('Scoring round still active; retry after it completes.')
        time.sleep(1)
    ctl('stop','summit-team-portal.service')
    with closing(sqlite3.connect(portal/'portal-state/portal.sqlite3')) as source,closing(sqlite3.connect(backup/'portal.sqlite3')) as target: source.backup(target)
    db_ready=True
    for index,target in enumerate([portal/'portal_store.py',score/'portal_store.py',portal/'arm_inject_schedule.py']):
        prior=backup/str(index); shutil.copy2(target,prior); saved.append((target,prior))
        temp=target.with_suffix('.update'); shutil.copy2(stage/target.name,temp); temp.chmod(0o600); temp.replace(target)
    sys.path.insert(0,str(portal))
    from portal_store import PortalStore
    store=PortalStore(portal/'portal-state/portal.sqlite3',score/'state/results.sqlite3',score/'config.json')
    with closing(sqlite3.connect(score/'state/results.sqlite3')) as db:
        before=db.execute('SELECT COUNT(*) FROM service_checks').fetchone()[0]
        event=db.execute('SELECT e.id,e.state FROM competition_events e JOIN scorer_settings s ON e.id=s.current_event_id WHERE s.id=1').fetchone()
    store.enable_event_template(2)
    state=store.snapshot(admin=True)
    assert state['event']['id']==event[0] and state['event']['state']==event[1]
    assert len(state['injects'])==6
    first=state['injects'][0]; assert first['code']=='I01' and first['released_at'] is not None and first['status']=='Grace period'
    assert first['scoring_starts_at']-first['released_at']==1800
    assert sum(c['earned_points'] for c in state['injects'])==0
    assert 'inject_template' not in state['settings']
    with closing(sqlite3.connect(score/'state/results.sqlite3')) as db: assert db.execute('SELECT COUNT(*) FROM service_checks').fetchone()[0]==before
    print({'repaired':True,'event_id':event[0],'event_state':event[1],'tasks':6,'I01':'released, full 30-minute grace','history_preserved':True,'backup':str(backup)})
except Exception:
    for target,prior in reversed(saved): shutil.copy2(prior,target)
    if db_ready and saved: shutil.copy2(backup/'portal.sqlite3',portal/'portal-state/portal.sqlite3')
    raise
finally:
    errors=[]
    for was_active,unit in [(running,'summit-team-portal.service'),(timer,'summit-check.timer')]:
        if was_active:
            try: ctl('start',unit)
            except subprocess.CalledProcessError: errors.append(unit)
    if errors: raise RuntimeError('Restart required: '+', '.join(errors))
