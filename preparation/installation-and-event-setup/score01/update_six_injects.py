"""Target-local incremental upgrade; preserve event, prior tasks and credentials."""
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

src=Path('/home/jwang/team-portal-package'); portal=Path('/home/jwang/summit-portal'); score=Path('/home/jwang/summit-scoring')
for name,digest in json.loads((src/'SHA256SUMS.json').read_text()).items():
    assert hashlib.sha256((src/name).read_bytes()).hexdigest()==digest,name
def ctl(*args): subprocess.run(['systemctl','--user',*args],check=True)
def active(name): return subprocess.run(['systemctl','--user','is-active','--quiet',name]).returncode==0
def evidence():
    with closing(sqlite3.connect((score/'state/results.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
        event=db.execute('SELECT e.id,e.state FROM competition_events e JOIN scorer_settings s ON s.current_event_id=e.id WHERE s.id=1').fetchone()
        return event, db.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0],db.execute('SELECT COUNT(*) FROM service_checks').fetchone()[0]
before=evidence(); assert before[0][1]=='STOPPED','Stop the event before this upgrade.'
with closing(sqlite3.connect(portal/'portal-state/portal.sqlite3')) as db:
    old=db.execute('SELECT * FROM injects WHERE event_id=? AND code IN (\'I01\',\'I02\',\'I03\',\'I04\') ORDER BY code',(before[0][0],)).fetchall()
timer=active('summit-check.timer'); running=active('summit-team-portal.service')
backup=Path('/home/jwang/portal-upgrade-backups')/('six-injects-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
backup.mkdir(mode=0o700,parents=True)
updates=[(score/name,src/name) for name in ['scorer.py','inject_services.py']]
updates += [(portal/name,src/name) for name in ['scorer.py','inject_services.py','portal_server.py','prepare_inject_resources.py','portal-injects.json','PORTAL-README.md','inject-resources/shipping-policy.txt','inject-resources/health.json']]
saved=[]
backup_ready=False
try:
    ctl('stop','summit-check.timer','summit-check.service','summit-team-portal.service')
    with closing(sqlite3.connect(portal/'portal-state/portal.sqlite3')) as source,closing(sqlite3.connect(backup/'portal.sqlite3')) as target: source.backup(target)
    shutil.copytree(portal/'portal-state/files/attachments',backup/'attachments')
    backup_ready=True
    for index,(target,source) in enumerate(updates):
        previous=backup/str(index)
        existed=target.exists()
        if existed: shutil.copy2(target,previous)
        saved.append((target,previous,existed))
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        shutil.copy2(source,target); target.chmod(0o600)
    subprocess.run(['/usr/bin/python3',str(portal/'portal_server.py'),'seed','--scoring',str(score/'state/results.sqlite3'),'--config',str(score/'config.json')],check=True)
    subprocess.run(['/usr/bin/python3',str(portal/'prepare_inject_resources.py')],check=True)
    assert evidence()==before,'Scoring state changed during upgrade.'
    with closing(sqlite3.connect(portal/'portal-state/portal.sqlite3')) as db:
        unchanged=db.execute('SELECT * FROM injects WHERE event_id=? AND code IN (\'I01\',\'I02\',\'I03\',\'I04\') ORDER BY code',(before[0][0],)).fetchall()
        assert unchanged==old,'Existing injects changed.'
        rows=db.execute('SELECT code,points,released_at FROM injects WHERE event_id=? ORDER BY code',(before[0][0],)).fetchall()
        assert len(rows)==6 and sum(row[1] for row in rows)==100
        assert all(row[2] is None for row in rows),'Tasks must remain drafts.'
except Exception:
    for target,previous,existed in reversed(saved):
        if existed: shutil.copy2(previous,target)
        elif target.exists(): target.unlink()
    if backup_ready and saved:
        restored=portal/'portal-state/files'/('attachments-restored-'+backup.name)
        failed=portal/'portal-state/files'/('attachments-failed-'+backup.name)
        shutil.copytree(backup/'attachments',restored)
        shutil.copy2(backup/'portal.sqlite3',portal/'portal-state/portal.sqlite3')
        (portal/'portal-state/portal.sqlite3').chmod(0o600)
        (portal/'portal-state/files/attachments').rename(failed)
        restored.rename(portal/'portal-state/files/attachments')
    raise
finally:
    failures=[]
    for was_running,service in [(running,'summit-team-portal.service'),(timer,'summit-check.timer')]:
        if was_running:
            try: ctl('start',service)
            except subprocess.CalledProcessError: failures.append(service)
    if failures: raise RuntimeError('Restore service state manually: '+', '.join(failures))
print(json.dumps({'updated':True,'drafts':6,'completion_points':100,'prior_injects_preserved':True,'event_state':before[0][1],'rounds':before[1],'checks':before[2],'backup':str(backup)}))
